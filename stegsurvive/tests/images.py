"""Deterministic synthetic test images (no copyrighted content). Helper, not a test."""
import functools

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _noise(rng, w, h):
    out = np.zeros((h, w))
    amp = 1.0
    for g in (128, 64, 32, 16, 8, 4):
        small = rng.random((h // g + 2, w // g + 2)).astype(np.float32)
        out += amp * np.asarray(Image.fromarray(small, "F").resize((w, h), Image.BICUBIC))
        amp /= 2
    return out


def _to_range(a, lo, hi):
    a = (a - a.min()) / (np.ptp(a) or 1)
    return lo + a * (hi - lo)


def plasma(w, h, seed=1):
    rng = np.random.default_rng(seed)
    rgb = np.stack([_to_range(_noise(rng, w, h), 20, 235) for _ in range(3)], -1)
    return Image.fromarray(rgb.round().astype(np.uint8), "RGB")


def scene(w, h, seed=2):
    rng = np.random.default_rng(seed)
    a = np.asarray(plasma(w, h, seed + 100), float).copy()
    sky = int(h * 0.4)
    t = np.linspace(0, 1, sky)[:, None, None]
    a[:sky] = (1 - t) * [70, 120, 200] + t * [190, 215, 240]
    img = Image.fromarray(a.round().astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    for _ in range(12):
        x, y = rng.integers(0, w), rng.integers(0, h)
        rx, ry = rng.integers(20, w // 5), rng.integers(20, h // 5)
        d.ellipse((x - rx, y - ry, x + rx, y + ry), fill=tuple(int(c) for c in rng.integers(0, 256, 3)))
    a = np.asarray(img, float) + rng.normal(0, 3, (h, w, 3))
    return Image.fromarray(np.clip(a, 0, 255).round().astype(np.uint8), "RGB")


def gradient(w, h):
    x = np.linspace(0, 1, w)[None, :]
    y = np.linspace(0, 1, h)[:, None]
    rgb = np.stack([40 + 180 * x + 0 * y, 40 + 180 * y + 0 * x, 220 - 90 * (x + y)], -1)
    return Image.fromarray(rgb.round().astype(np.uint8), "RGB")


def screenshot(w, h, seed=3):
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for y in range(40, h - 30, 28):
        x = 40
        while x < w - 80:
            word = int(rng.integers(20, 90))
            d.rectangle((x, y, min(x + word, w - 40), y + 12), fill=(60, 60, 60))
            x += word + int(rng.integers(8, 16))
            if rng.random() < 0.08:
                break
    return img


def _pink(rng, w, h):
    """1/f amplitude spectrum noise (natural-image statistics), zero mean, unit std."""
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    f = np.hypot(fx, fy)
    f[0, 0] = 1
    spec = (rng.normal(size=f.shape) + 1j * rng.normal(size=f.shape)) / f
    spec[0, 0] = 0
    a = np.fft.irfft2(spec, (h, w))
    return a / a.std()


def fractal(w, h, seed=4):
    """Photo-like: 1/f texture, colored by a smooth palette, with soft-edged (blurred) blobs."""
    rng = np.random.default_rng(seed)
    base = _pink(rng, w, h)
    rgb = np.stack([128 + 38 * (base + 0.35 * _pink(rng, w, h)) + off for off in rng.normal(0, 20, 3)], -1)
    for _ in range(6):
        m = Image.new("L", (w, h), 0)
        x, y = rng.integers(0, w), rng.integers(0, h)
        rx, ry = rng.integers(w // 12, w // 4), rng.integers(h // 12, h // 4)
        ImageDraw.Draw(m).ellipse((x - rx, y - ry, x + rx, y + ry), fill=255)
        m = np.asarray(m.filter(ImageFilter.GaussianBlur(rng.uniform(4, 25))), float)[..., None] / 255
        color = rng.integers(30, 226, 3) + 12 * _pink(rng, w, h)[..., None]
        rgb = rgb * (1 - m) + color * m
    return Image.fromarray(np.clip(rgb, 0, 255).round().astype(np.uint8), "RGB")


@functools.cache
def natural():
    return [("plasma", plasma(960, 720)), ("scene", scene(720, 1280)), ("gradient", gradient(960, 720)),
            ("fractal", fractal(1280, 720)), ("fractal2", fractal(720, 960, seed=5))]
