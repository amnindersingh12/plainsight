"""Finding type, limits and small helpers shared by every check."""
import re
from dataclasses import dataclass
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

from PIL import Image

SCORE_FLAG, SCORE_FILE, SCORE_TEXT, SCORE_ANOMALY, SCORE_INFO, SCORE_NOTE = 100, 80, 50, 40, 10, 0

MAX_INPUT_BYTES = 200 * 2**20
MAX_IMAGE_PIXELS = 40_000_000
MAX_EXTRACT_BYTES = 50 * 2**20
MAX_LSB_BYTES = 2**20
MAX_SHOWN = 15
TOOL_TIMEOUT = 120
MAX_TOOL_OUTPUT = 64 * 1024
DEFAULT_FLAG_FORMAT = r"(?i)\b\w{0,12}(?:flag|ctf|htb|thm)\{[^\s{}]{1,200}\}"
# Known full flag names: a default-regex match is trimmed to start at the last one, so text glued in front
# ("flag.txtpicoCTF{...}") is dropped while unknown team prefixes ("xyzctf{...}") are kept.
_KNOWN_NAME = re.compile(r"(?i)(?:(?:pico|du)ctf|flag|htb|thm)\{")
SIGNATURES = {"zip": b"PK\x03\x04", "png": b"\x89PNG\r\n\x1a\n", "jpg": b"\xff\xd8\xff", "pdf": b"%PDF-",
              "7z": b"7z\xbc\xaf\x27\x1c", "gz": b"\x1f\x8b\x08", "elf": b"\x7fELF"}

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
# Only the decoders we route to; keeps Pillow away from e.g. EPS (Ghostscript) on untrusted input.
IMAGE_FORMATS = ("PNG", "JPEG", "GIF", "BMP", "TIFF", "WEBP")


@dataclass
class Finding:
    check: str
    title: str
    score: int
    detail: str = ""
    blob: bytes | memoryview | None = None
    name: str | None = None


def clean(s: str, limit: int = 120) -> str:
    out = "".join(c if c.isprintable() else f"\\x{ord(c):02x}" if ord(c) <= 0xFF else f"\\u{ord(c):04x}" for c in s)
    return out[:limit] + "..." if len(out) > limit else out


def find_flags(data: bytes, flag_re: re.Pattern[str]) -> list[str]:
    # ponytail: ~0.1 s per MiB of noisy data with the default regex (about 14 s for a 12 Mpx RGBA LSB sweep);
    # add a literal prefilter if big images get common
    found: dict[str, None] = {}
    trim = flag_re.pattern == DEFAULT_FLAG_FORMAT  # a user's --flag-format is used as-is
    for m in flag_re.finditer(data.decode("latin-1")):
        flag = m.group(0)
        known = _KNOWN_NAME.search(flag) if trim else None
        found[flag[known.start():] if known else flag] = None
        if len(found) == 20:
            break
    return list(found)


def printable_runs(data: bytes, min_len: int = 8) -> Iterator[str]:
    return (m.group().decode("ascii") for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data))


def sniff(data: bytes) -> str:
    if data.startswith(SIGNATURES["png"]):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data.startswith(b"BM"):
        return "bmp"
    if data[:4] in (b"II*\0", b"MM\0*"):
        return "tiff"
    if data[:4] == b"RIFF" and data[8:12] in (b"WEBP", b"WAVE"):
        return "webp" if data[8:12] == b"WEBP" else "wav"
    return "other"


def open_image(data: bytes) -> Image.Image:
    # Pillow's own open-time bomb check would raise first, without the dimensions; ours runs instead,
    # and Pillow's limit is back on for every later decode (frames, tiles).
    Image.MAX_IMAGE_PIXELS = None
    try:
        img = Image.open(BytesIO(data), formats=IMAGE_FORMATS)
    finally:
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    w, h = img.size
    if w * h > MAX_IMAGE_PIXELS:
        raise ValueError(f"image too large: {w}x{h} > {MAX_IMAGE_PIXELS} pixels")
    return img


def rank(findings: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in findings:
        if (f.check, f.title) not in seen:
            seen.add((f.check, f.title))
            out.append(f)
    return sorted(out, key=lambda f: -f.score)


def save_artifact(out_dir: Path, name: str, blob: bytes | memoryview) -> Path:
    rel = Path(name)
    if rel.is_absolute() or rel.anchor or ".." in rel.parts:
        raise ValueError(f"unsafe artifact name: {name!r}")
    target = (out_dir / rel).resolve()
    if not target.is_relative_to(out_dir.resolve()):
        raise ValueError(f"artifact path escapes report dir: {name!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob[:MAX_EXTRACT_BYTES])
    return target
