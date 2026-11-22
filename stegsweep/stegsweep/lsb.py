"""zsteg-style LSB sweep for images and WAV audio, plus stegsolve-style bit-plane images."""
import re
import wave
from io import BytesIO
from math import ceil
from pathlib import Path

from PIL import Image

from .core import (MAX_LSB_BYTES, SCORE_FILE, SCORE_FLAG, SCORE_NOTE, SCORE_TEXT, SIGNATURES, Finding, clean,
                   find_flags)

_TO_ASCII = bytes.maketrans(b"\0\1", b"01")
_REVERSED_BITS = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
_LOW_BIT = bytes(i & 1 for i in range(256))
_MERGE_MODES = {2: "LA", 3: "RGB", 4: "RGBA"}
MAX_BITS = MAX_LSB_BYTES * 8  # ponytail: scans first MAX_LSB_BYTES per config, raise it if hidden files get truncated


def channel_orders(bands: tuple[str, ...]) -> list[str]:
    lower = [b.lower() for b in bands]
    out = list(lower)
    if len(lower) > 1:
        color = [b for b in lower if b != "a"]
        if "a" in lower and len(color) >= 3:
            out += ["".join(color), "".join(reversed(color))]
        out += ["".join(lower), "".join(reversed(lower))]
    return out


def _normalize(img: Image.Image) -> Image.Image:
    mode = img.mode
    if mode == "1":
        return img.convert("L")
    if mode == "P":  # palette indices are where palette steg hides, not the RGB they map to
        return Image.frombytes("L", img.size, img.tobytes())
    if mode in ("L", "LA", "RGB", "RGBA"):
        return img
    if mode in ("I", "F") or mode.startswith("I;16"):
        return img.convert("L")  # clips, fine for triage
    return img.convert("RGBA" if "A" in img.getbands() else "RGB")


def _pack(bits: bytes) -> bytes:
    n = len(bits) // 8 * 8
    # base-2 int() is linear and exempt from the 3.11+ digit limit
    return int(bits[:n].translate(_TO_ASCII), 2).to_bytes(n // 8, "big") if n else b""


def _finding(check: str, config: str, stream: bytes, flag_re: re.Pattern[str]) -> Finding | None:
    flags = find_flags(stream, flag_re)
    ext = next((e for e, sig in SIGNATURES.items() if stream.startswith(sig)), None)
    run = re.match(rb"[\x20-\x7e]{8,}", stream)
    if flags:
        title, score = clean(f"{config}: {flags[0]}"), SCORE_FLAG
    elif ext:
        title, score = f"{config}: {ext} file", SCORE_FILE
    elif run and len(set(run.group())) >= 4:
        title, score = clean(f'{config}: text "{run.group()[:80].decode("ascii")}"'), SCORE_TEXT
    else:
        return None
    return Finding(check, title, score, blob=stream, name="lsb/" + config.replace(",", "_") + ".bin")


def _streams(config: str, bits: bytes, check: str, flag_re: re.Pattern[str]) -> list[Finding]:
    packed = _pack(bits)
    found = [_finding(check, f"{config},msbfirst", packed, flag_re),
             _finding(check, f"{config},lsbfirst", packed.translate(_REVERSED_BITS), flag_re)]
    return [f for f in found if f]


def sweep_image(img: Image.Image, flag_re: re.Pattern[str]) -> list[Finding]:
    img = _normalize(img)
    names = [b.lower() for b in img.getbands()]
    out = []
    for order in ("xy", "yx"):
        base = img if order == "xy" else img.transpose(Image.Transpose.TRANSPOSE)
        w, h = base.size
        base = base.crop((0, 0, w, min(h, ceil(MAX_BITS / w))))  # no config needs more rows than this
        bands = dict(zip(names, base.split()))
        plane0: dict[str, bytes] = {}
        for plane in range(3):
            lut = [(v >> plane) & 1 for v in range(256)]
            planes = {k: band.point(lut) for k, band in bands.items()}
            for chans in channel_orders(tuple(names)):
                rows = min(base.size[1], ceil(MAX_BITS / (w * len(chans))))
                sel = [planes[c].crop((0, 0, w, rows)) for c in chans]
                bits = sel[0].tobytes() if len(sel) == 1 else Image.merge(_MERGE_MODES[len(sel)], sel).tobytes()
                out += _streams(f"bit{plane},{chans},{order}", bits[:MAX_BITS], "lsb", flag_re)
                if len(chans) >= 3 and plane == 0:
                    plane0[chans] = bits
                elif len(chans) >= 3 and plane == 1:  # zsteg b2: bit 1 then bit 0 of each channel value
                    two = bytearray(2 * len(bits))
                    two[0::2], two[1::2] = bits, plane0.pop(chans)
                    out += _streams(f"bit0-1,{chans},{order}", bytes(two[:MAX_BITS]), "lsb", flag_re)
    return out


def sweep_wav(data: bytes, flag_re: re.Pattern[str]) -> list[Finding]:
    with wave.open(BytesIO(data)) as w:
        width, nch = w.getsampwidth(), w.getnchannels()
        if width not in (1, 2):
            return [Finding("wav-lsb", f"unsupported sample width {width}", SCORE_NOTE)]
        raw = w.readframes(min(w.getnframes(), ceil(MAX_BITS / nch)))
    # 8-bit samples are one byte; 16-bit are little-endian, so the LSB lives in the first byte of each
    bits = raw[::width][:MAX_BITS].translate(_LOW_BIT)
    return _streams("wav,bit0", bits, "wav-lsb", flag_re)


def save_bit_planes(img: Image.Image, out_dir: Path) -> list[Path]:
    img = _normalize(img)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, band in zip(img.getbands(), img.split()):
        for plane in range(8):
            path = out_dir / f"{name.upper()}{plane}.png"
            band.point([255 if (v >> plane) & 1 else 0 for v in range(256)]).save(path)
            paths.append(path)
    return paths
