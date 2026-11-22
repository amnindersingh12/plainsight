"""File-level checks: metadata, trailing data, embedded signatures, strings, PNG chunks."""
import re
import struct
import zipfile
import zlib
from io import BytesIO
from itertools import islice

from PIL import ExifTags

from .core import (MAX_EXTRACT_BYTES, SCORE_ANOMALY, SCORE_FILE, SCORE_FLAG, SCORE_INFO, SCORE_NOTE, SCORE_TEXT,
                   SIGNATURES, Finding, clean, find_flags, open_image, printable_runs, sniff)

CARVE_BUDGET = 4 * MAX_EXTRACT_BYTES  # total bytes carved per input
ZIP_MEMBER_CAP = MAX_EXTRACT_BYTES  # bytes read per zip member, whatever its header declares
ZIP_BUDGET = 4 * MAX_EXTRACT_BYTES  # bytes read from all zip members together
MAX_ZIP_MEMBERS = 1000
PNG_TYPES = set(b"IHDR PLTE IDAT IEND tRNS cHRM gAMA iCCP sBIT sRGB cICP mDCV cLLI tEXt zTXt iTXt bKGD hIST pHYs "
                b"sPLT eXIf tIME acTL fcTL fdAT oFFs pCAL sCAL".split())


def _exif_text(tag: int, value) -> str:
    if not isinstance(value, bytes):
        return str(value)
    if 0x9C9B <= tag <= 0x9C9F:  # Windows XPTitle/XPComment/XPAuthor/XPKeywords/XPSubject: UTF-16LE
        return value.decode("utf-16le", "replace").rstrip("\0")
    if tag == 0x9286 and value[:8] == b"UNICODE\0":  # UserComment: 8-byte charset, then UCS-2 in file byte order
        body = value[8:]
        return body.decode("utf-16be" if body[::2].count(0) > body[1::2].count(0) else "utf-16le", "replace").rstrip("\0")
    if tag == 0x9286 and value[:8] in (b"ASCII\0\0\0", b"\0" * 8):
        value = value[8:]
    return value.decode("latin-1").rstrip("\0")


def check_metadata(data: bytes, flag_re: re.Pattern[str]) -> list[Finding]:
    img = open_image(data)  # pixel limit already checked, so load() is bounded
    out = []
    try:
        img.load()  # PNG text chunks after IDAT only reach img.info once the pixels are read
    except Exception as exc:  # truncated pixels: keep the metadata read so far
        out.append(Finding("metadata", clean(f"pixel data unreadable, later metadata skipped: {exc}"), SCORE_NOTE))
    for key, value in img.info.items():
        if isinstance(value, bytes) and key in ("comment", "xmp"):
            value = value.decode("latin-1")
        if not isinstance(value, str):
            continue
        flags = find_flags(value.encode("latin-1", "replace"), flag_re)
        out += [Finding("metadata", clean(f"{key}: {flag}"), SCORE_FLAG, value) for flag in flags]
        if not flags:
            out.append(Finding("metadata", clean(f"{key}: {value}"), SCORE_TEXT, value))
    exif = img.getexif()
    for tag, value in [*exif.items(), *exif.get_ifd(0x8769).items()]:
        if tag == 0x8769:  # pointer to the sub-IFD read above
            continue
        name = ExifTags.TAGS.get(tag, f"0x{tag:04x}")
        text = _exif_text(tag, value)
        flags = find_flags(text.encode("latin-1", "replace"), flag_re) if isinstance(value, (str, bytes)) else []
        out += [Finding("metadata", clean(f"EXIF {name}: {flag}"), SCORE_FLAG, text) for flag in flags]
        if not flags:
            out.append(Finding("metadata", clean(f"EXIF {name}: {text}"), SCORE_INFO, text))
    return out


def _png_walk(data: bytes):
    """Yield (offset, type, body, stored_crc) up to and including IEND; type None means truncated at offset."""
    view, off = memoryview(data), 8
    while True:
        if off + 12 > len(data):
            yield off, None, None, None
            return
        length, ctype = struct.unpack_from(">I4s", data, off)
        if off + 12 + length > len(data):
            yield off, None, None, None
            return
        yield off, ctype, view[off + 8:off + 8 + length], struct.unpack_from(">I", data, off + 8 + length)[0]
        if ctype == b"IEND":
            return
        off += 12 + length


def _png_end(data: bytes) -> int | None:
    for off, ctype, body, _ in _png_walk(data):
        if ctype == b"IEND":
            return off + 12 + len(body)
    return None


_FILL = re.compile(rb"\xff+")
_ECS_MARKER = re.compile(rb"\xff(?=[^\x00\xd0-\xd7])")  # in entropy-coded data FF00 is a stuffed byte, FFD0-7 restarts


def _jpeg_end(data: bytes) -> int | None:
    i, n = 2, len(data)
    while True:
        fill = _FILL.match(data, i)  # a marker is one or more FF bytes, then its code
        if not fill or fill.end() >= n:
            return None
        i = fill.end() - 1
        m = data[i + 1]
        if m == 0xD9:
            return i + 2
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            i += 2
            continue
        if i + 4 > n:
            return None
        seglen = struct.unpack_from(">H", data, i + 2)[0]
        if seglen < 2:
            return None
        i += 2 + seglen
        if m == 0xDA:  # entropy-coded data follows SOS: jump to the next real marker
            nxt = _ECS_MARKER.search(data, i)
            if not nxt:
                return None
            i = nxt.start()


def check_trailing(data: bytes) -> list[Finding]:
    kind = sniff(data)
    if kind == "png":
        end, label = _png_end(data), "PNG IEND"
    elif kind == "jpeg":
        end, label = _jpeg_end(data), "JPEG EOI"
    else:
        return []
    if end is None or end >= len(data):
        return []
    ext = next((e for e, sig in SIGNATURES.items() if data.startswith(sig, end)), None)
    title = f"{len(data) - end} bytes after {label} at {end:#x}" + (f" ({ext} data)" if ext else "")
    return [Finding("trailing", title, SCORE_FILE, blob=memoryview(data)[end:end + MAX_EXTRACT_BYTES],
                    name="trailing.bin")]


def _zip_end(data: bytes, off: int) -> int | None:
    eocd = data.find(b"PK\x05\x06", off)
    return eocd + 22 + struct.unpack_from("<H", data, eocd + 20)[0] if 0 <= eocd <= len(data) - 22 else None


def check_signatures(data: bytes) -> list[Finding]:
    hits = []
    for ext, sig in SIGNATURES.items():
        off = 0
        for _ in range(5):
            off = data.find(sig, off + 1)
            if off < 0:
                break
            hits.append((off, ext))
    hits.sort()
    out, budget = [], CARVE_BUDGET
    for k, (off, ext) in enumerate(hits):
        # no format parsing: a carve runs to the next signature, a zip to its end-of-central-directory record
        end = (_zip_end(data, off) if ext == "zip" else None) or (hits[k + 1][0] if k + 1 < len(hits) else len(data))
        end = min(end, len(data), off + MAX_EXTRACT_BYTES)
        if end - off > budget:
            out.append(Finding("signature", f"carving stopped at {off:#x}: {CARVE_BUDGET}-byte budget used", SCORE_NOTE))
            break
        budget -= end - off
        out.append(Finding("signature", f"{ext} at {off:#x}", SCORE_FILE, blob=memoryview(data)[off:end],
                           name=f"carved/{off:08x}.{ext}"))
    return out


def _zip_member(info: zipfile.ZipInfo, content: bytes, capped: bool, label: str, flag_re) -> list[Finding]:
    name = clean(info.filename, 60)
    first = list(islice(printable_runs(content), 2000))
    out = [Finding("zip", clean(f"zip:{name}: {flag}"), SCORE_FLAG) for flag in find_flags(content, flag_re)]
    out.append(Finding("zip", f"zip:{name}: {len(content)} bytes" + (" (capped)" if capped else ""),
                       SCORE_TEXT if first else SCORE_INFO, "\n".join(first), blob=content, name=label))
    return out


def check_zip_members(data: bytes, flag_re: re.Pattern[str]) -> list[Finding]:
    """Search inside embedded zips, in memory only; members are read, never written or executed."""
    out, budget, seen, off = [], ZIP_BUDGET, set(), -1
    for _ in range(5):
        off = data.find(SIGNATURES["zip"], off + 1)
        if off < 0:
            break
        end = _zip_end(data, off)
        if end is None or end in seen:  # later local headers of an archive already read share its end
            continue
        seen.add(end)
        try:
            zf = zipfile.ZipFile(BytesIO(data[off:end]))
        except Exception as exc:
            out.append(Finding("zip", clean(f"zip at {off:#x} unreadable: {exc}"), SCORE_NOTE))
            continue
        with zf:
            for k, info in enumerate(zf.infolist()):
                name = clean(info.filename, 60)
                if k == MAX_ZIP_MEMBERS or budget <= 0:
                    out.append(Finding("zip", f"zip at {off:#x}: stopped at member {k} (member or byte limit)",
                                       SCORE_NOTE))
                    break
                if info.flag_bits & 1:
                    out.append(Finding("zip", f"encrypted zip member {name} (try a wordlist: zip2john / fcrackzip)",
                                       SCORE_ANOMALY))
                    continue
                cap = min(ZIP_MEMBER_CAP, budget)
                try:
                    with zf.open(info) as fh:  # read(cap) decompresses incrementally: a bomb stops at cap
                        content = fh.read(cap)
                        capped = len(content) == cap and fh.read(1) != b""
                except Exception as exc:  # bad CRC, unsupported method, truncated stream
                    out.append(Finding("zip", clean(f"zip:{name}: unreadable: {exc}"), SCORE_NOTE))
                    continue
                budget -= len(content)
                out += _zip_member(info, content, capped, f"zip/{off:08x}_{k:04d}.bin", flag_re)
    return out


def check_strings(data: bytes, flag_re: re.Pattern[str]) -> list[Finding]:
    out = [Finding("strings", clean(f"raw: {flag}"), SCORE_FLAG) for flag in find_flags(data, flag_re)]
    runs = printable_runs(data)
    first = list(islice(runs, 2000))
    n = len(first) + sum(1 for _ in runs)  # stream the rest: keeping every run costs ~15x the input
    if n:
        out.append(Finding("strings", f"{n} printable strings (8+ chars)", SCORE_INFO, "\n".join(first)))
    return out


def check_png_chunks(data: bytes) -> list[Finding]:
    out = []
    for off, ctype, body, stored in _png_walk(data):
        if ctype is None:
            out.append(Finding("png-chunks", f"truncated chunk at {off:#x}", SCORE_ANOMALY))
            break
        t = ctype.decode("latin-1")
        computed = zlib.crc32(body, zlib.crc32(ctype))
        if stored != computed:
            out.append(Finding("png-chunks", clean(f"{t} CRC mismatch (stored {stored:#010x}, computed {computed:#010x})"),
                               SCORE_ANOMALY))
        if ctype not in PNG_TYPES:
            safe = t if re.fullmatch(r"[A-Za-z]{4}", t) else ctype.hex()
            out.append(Finding("png-chunks", clean(f"unknown chunk '{t}' ({len(body)} bytes)"), SCORE_ANOMALY,
                               blob=body, name=f"chunks/{off:08x}_{safe}.bin"))
    return out
