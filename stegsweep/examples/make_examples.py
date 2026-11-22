"""Regenerate the practice challenges in this folder: `python examples/make_examples.py`.

Every cover image is drawn here (no photos), so the files are free to share and reproducible.
"""
import io
import math
import random
import struct
import wave
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo

HERE = Path(__file__).parent
W, H = 480, 270


def scene(sky_top, sky_bottom, sun, hills, stars=False):
    """Gradient sky, a sun or moon, and layered sine hills."""
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(sky_top, sky_bottom)))
    if stars:
        rng = random.Random(7)   # fixed seed: same picture every run
        for _ in range(90):
            x, y = rng.randrange(W), rng.randrange(H * 2 // 3)
            d.point((x, y), fill=(230, 230, 255))
    cx, cy, r, color = sun
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    for k, (base, amp, freq, color) in enumerate(hills):
        pts = [(x, base + amp * math.sin(x * freq + k * 1.7)) for x in range(0, W + 8, 8)]
        d.polygon(pts + [(W, H), (0, H)], fill=color)
    return img


def bits(message: bytes):
    return [(b >> (7 - i)) & 1 for b in message for i in range(8)]


def lsb_png():
    img = scene((70, 130, 200), (250, 200, 150), (360, 80, 28, (255, 236, 160)),
                [(190, 14, 0.020, (90, 140, 90)), (215, 10, 0.031, (60, 110, 70)), (240, 8, 0.045, (40, 80, 55))])
    flat = bytearray(img.tobytes())
    for i, b in enumerate(bits(b"flag{lsb_in_the_sky}\x00")):
        flat[i] = (flat[i] & ~1) | b
    Image.frombytes("RGB", img.size, bytes(flat)).save(HERE / "01-sky.png", optimize=True)


def zip_jpeg():
    img = scene((40, 30, 80), (250, 120, 80), (240, 200, 40, (255, 210, 120)),
                [(205, 12, 0.018, (70, 40, 70)), (230, 9, 0.029, (45, 25, 50))])
    jpg = io.BytesIO()
    img.save(jpg, "JPEG", quality=85)
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        f.writestr("flag.txt", "picoCTF{z1p_4ft3r_th3_3nd}\n")
        f.writestr("readme.txt", "nothing to see here\n" * 20)
    (HERE / "02-sunset.jpg").write_bytes(jpg.getvalue() + z.getvalue())


def text_png():
    img = scene((5, 10, 35), (30, 40, 90), (120, 60, 20, (235, 235, 210)),
                [(200, 10, 0.022, (20, 30, 45)), (228, 8, 0.035, (10, 18, 30))], stars=True)
    info = PngInfo()
    info.add_text("Author", "night owl")
    info.add_text("Comment", "CTF{c0mpr3ss3d_c0mm3nts}", zip=True)   # zTXt: not visible to plain `strings`
    img.save(HERE / "03-night.png", pnginfo=info, optimize=True)


def wav_lsb():
    msg = bits(b"flag{l1st3n_t0_th3_l0w_b1ts}\x00")
    rate, n = 8000, 8000
    samples = []
    for i in range(n):
        s = int(9000 * math.sin(2 * math.pi * 440 * i / rate) * math.exp(-3 * i / n))
        samples.append((s & ~1) | (msg[i] if i < len(msg) else s & 1))
    with wave.open(str(HERE / "04-beep.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{n}h", *samples))


def exif_jpeg():
    img = scene((150, 190, 230), (225, 235, 245), (90, 70, 22, (255, 250, 230)),
                [(150, 30, 0.012, (120, 130, 150)), (200, 18, 0.025, (85, 100, 120)), (240, 8, 0.04, (60, 90, 70))])
    exif = Image.Exif()
    exif[0x0110] = "PlainCam 1"                                   # Model
    exif[0x9C9C] = "HTB{3x1f_t4lk5_t00}".encode("utf-16le") + b"\0\0"   # XPComment: UTF-16, so no ASCII string
    img.save(HERE / "05-mountains.jpg", "JPEG", quality=85, exif=exif)


if __name__ == "__main__":
    for make in (lsb_png, zip_jpeg, text_png, wav_lsb, exif_jpeg):
        make()
    for p in sorted(HERE.iterdir()):
        if p.suffix != ".py":
            print(f"{p.name:16} {p.stat().st_size:>7} bytes")
