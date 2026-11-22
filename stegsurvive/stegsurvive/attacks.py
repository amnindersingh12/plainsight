"""Simulated attacks: recompression, resizing, cropping and guessed platform pipelines."""
from io import BytesIO

from PIL import Image


def _encode(img, fmt, q):
    buf = BytesIO()
    img.convert("RGB").save(buf, fmt, quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def jpeg(img, q):
    return _encode(img, "JPEG", q)


def webp(img, q):
    return _encode(img, "WEBP", q)


def scale(img, f):
    w, h = img.size
    return img.convert("RGB").resize((round(w * f), round(h * f)), Image.LANCZOS)


def fit(img, max_side):
    w, h = img.size
    if max(w, h) <= max_side:
        return img.convert("RGB")
    return scale(img, max_side / max(w, h))


def crop(img, frac=0.05):
    w, h = img.size
    return img.convert("RGB").crop((0, 0, round(w * (1 - frac)), round(h * (1 - frac))))


# (max_side, jpeg_q): documented guesses from public write-ups, NOT measured against the real apps.
PLATFORMS = {"whatsapp": (1600, 70), "telegram": (1280, 80), "x": (2048, 85), "instagram": (1080, 75),
             "facebook": (2048, 71)}

# (name, required, fn): required attacks are the v1 done criteria; the others are measured only.
ATTACKS = (
    [(f"jpeg{q}", True, lambda im, q=q: jpeg(im, q)) for q in (95, 90, 80, 70, 60)]
    + [(f"resize{p}+jpeg80", True, lambda im, p=p: jpeg(scale(im, p / 100), 80)) for p in (75, 50)]
    + [("webp80", True, lambda im: webp(im, 80))]
    + [(n, True, lambda im, s=s, q=q: jpeg(fit(im, s), q)) for n, (s, q) in PLATFORMS.items()]
    + [("jpeg50", False, lambda im: jpeg(im, 50)), ("crop5", False, crop)]
)
