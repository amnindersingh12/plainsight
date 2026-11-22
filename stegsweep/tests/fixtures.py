"""Synthetic test files. `python tests/fixtures.py DIR` writes the demo files into DIR."""
import io
import struct
import sys
import wave
import zipfile
import zlib
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

FLAG = "picoCTF{l5b_15_n0t_s3cr3t}"


def _bits(message: bytes) -> list[int]:
    return [(b >> (7 - i)) & 1 for b in message for i in range(8)]


def make_png_lsb(d: Path, message: bytes = FLAG.encode()) -> Path:
    bits = _bits(message + b"\x00")
    img = Image.new("RGB", (64, 64))
    flat = [v for y in range(64) for x in range(64) for v in ((x * 4) % 256, (y * 4) % 256, 128)]
    assert len(bits) <= len(flat), "message too long for 64x64"
    for i, bit in enumerate(bits):
        flat[i] = (flat[i] & ~1) | bit
    img.frombytes(bytes(flat))
    path = Path(d) / "lsb.png"
    img.save(path)
    return path


def make_png_text(d: Path, text: str = FLAG) -> Path:
    info = PngInfo()
    info.add_text("Comment", text)
    info.add_text("Author", "alice")
    path = Path(d) / "text.png"
    Image.new("RGB", (16, 16), (40, 80, 120)).save(path, pnginfo=info)
    return path


def jpeg_bytes(size=(32, 32), **save_kwargs) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, "JPEG", **{"quality": 90, **save_kwargs})
    return buf.getvalue()


def png_bytes(size=(16, 16), mode="RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size).save(buf, "PNG")
    return buf.getvalue()


def make_jpeg_with_zip(d: Path) -> tuple[Path, int, bytes]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("flag.txt", FLAG)
    jpg, zdata = jpeg_bytes(), buf.getvalue()
    path = Path(d) / "zip.jpg"
    path.write_bytes(jpg + zdata)
    return path, len(jpg), zdata


def make_wav_lsb(d: Path, message: bytes = FLAG.encode()) -> Path:
    bits = _bits(message + b"\x00")
    samples = [(((i * 37) % 2000 - 1000) & ~1) | (bits[i] if i < len(bits) else 0) for i in range(4000)]
    path = Path(d) / "lsb.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def png_chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", zlib.crc32(ctype + body))


def insert_before_iend(png: bytes, chunk: bytes) -> bytes:
    return png[:-12] + chunk + png[-12:]


def png_with_size(w: int, h: int) -> bytes:
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + png_chunk(b"IEND", b""))


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for p in (make_png_lsb(out), make_png_text(out), make_jpeg_with_zip(out)[0], make_wav_lsb(out)):
        print(p)
