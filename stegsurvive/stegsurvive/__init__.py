"""stegsurvive: hidden messages that survive social media recompression and resizing.

hide(image, message, password=None) -> image; reveal(image, password=None) -> bytes.
"""
import hashlib
import os
import warnings
import zlib

import numpy as np
from PIL import Image, ImageOps

from . import attacks, core, rs

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # optional extra: pip install stegsurvive[crypto]
    AESGCM = None
    InvalidTag = None

__all__ = ["hide", "reveal", "RevealError", "CAPACITY", "AES_CAPACITY", "XOR_CAPACITY"]

CAPACITY = 64  # bytes, fixed for every image size
AES_CAPACITY = CAPACITY - 28  # 12-byte nonce + 16-byte tag
XOR_CAPACITY = CAPACITY - 8  # 8-byte random nonce, so a password never reuses a keystream
NSYM = 32  # RS parity bytes: corrects 16 byte errors in the 102-byte codeword
FRAME = 2 + CAPACITY + 4  # header (version|mode, length) + data + CRC32
NBITS = (FRAME + NSYM) * 8  # 816
VERSION = 1
PLAIN, XOR, AES = 0, 1, 2
MIN_SIDE, GOOD_SIDE = 256, 720
MAX_PIXELS = 50_000_000  # ponytail: full-res float math, ~70 B/pixel peak RSS; tile if bigger is needed


class RevealError(ValueError):
    """No message could be recovered (absent, destroyed, or wrong password)."""


def _key(password):
    if password is None:
        return core.DEFAULT_KEY
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    # ponytail: fixed salt, there is no room for a per-message salt in 64 bytes; scrypt slows guessing
    return hashlib.scrypt(password.encode(), salt=b"stegsurvive-v1", n=2 ** 14, r=8, p=1, dklen=32)


def _xor(data, key, nonce):
    return bytes(a ^ b for a, b in zip(data, core.stream(key, b"xor" + nonce, len(data))))


def _open(image):
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL.Image.Image")
    if image.width * image.height > MAX_PIXELS:
        raise ValueError(f"image too large: {image.width * image.height / 1e6:.0f} MP, max 50 MP")
    return ImageOps.exif_transpose(image)  # upright pixels, so a platform cannot rotate the grid


def _flatten(img):
    """Composite transparency onto white, as platforms do, so the mark is made on what they show."""
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGBA", img.size, "white")
        bg.alpha_composite(img.convert("RGBA"))
        return bg.convert("RGB"), True
    return img, False


def hide(image, message, password=None):
    """Return a copy of `image` carrying `message` (bytes, or str as UTF-8)."""
    if isinstance(message, str):
        message = message.encode("utf-8")
    elif isinstance(message, (bytes, bytearray, memoryview)):
        message = bytes(message)
    else:
        raise TypeError("message must be bytes or str")
    img = _open(image)
    if min(img.size) < MIN_SIDE:
        raise ValueError(f"image too small: short side must be >= {MIN_SIDE} px")
    if min(img.size) < GOOD_SIDE:
        warnings.warn(f"short side < {GOOD_SIDE} px: the robustness targets assume >= {GOOD_SIDE} px",
                      UserWarning, stacklevel=2)
    key = _key(password)
    mode = PLAIN if password is None else XOR if AESGCM is None else AES
    cap = {PLAIN: CAPACITY, XOR: XOR_CAPACITY, AES: AES_CAPACITY}[mode]
    if len(message) > cap:
        raise ValueError(f"message is {len(message)} bytes; capacity is {cap} bytes")
    if mode == XOR:
        warnings.warn("cryptography is not installed: the password only obfuscates the message "
                      "(pip install stegsurvive[crypto] for AES-GCM)", UserWarning, stacklevel=2)
        nonce = os.urandom(8)
        data = nonce + _xor(message, key, nonce)
    elif mode == AES:
        nonce = os.urandom(12)
        data = nonce + AESGCM(key).encrypt(nonce, message, None)
    else:
        data = message
    head = bytes([VERSION << 4 | mode, len(data)]) + data.ljust(CAPACITY, b"\0")
    code = rs.encode(head + zlib.crc32(head).to_bytes(4, "big"), NSYM)
    bits = np.unpackbits(np.frombuffer(code, np.uint8))

    img, flattened = _flatten(img)
    if flattened:
        warnings.warn("transparency flattened onto white (platforms flatten it too); output is RGB",
                      UserWarning, stacklevel=2)
    rgb = np.asarray(img.convert("RGB"))
    # Pure white/black pixels cannot move both ways, so screenshots, documents and black borders carry
    # almost nothing at default settings. Retry with them nudged 2 levels inward (invisible) and the
    # change allowed closer to the extremes; the decoder needs no hint. Ordinary photos pass first try.
    # A result is accepted only if it also reads back after a harsh trip (half size + JPEG 80): reading the
    # untouched file proves little, and some screenshots pass that but break in the apps.
    fallback = None
    for head, taper in ((0, core.TAPER), (2, 8.0)):
        src = np.clip(rgb, head, 255 - head) if head else rgb
        out = Image.fromarray(core.embed(src, bits, key, taper), "RGB")
        if img.mode == "L":
            out = out.convert("L")
        if _reads(out, message, password):  # never report success for a message that does not read back
            if _reads(attacks.jpeg(attacks.scale(out, 0.5), 80), message, password):
                return out
            fallback = fallback or out
    if fallback is not None:
        warnings.warn("the message reads back from this file but may not survive heavy recompression or "
                      "resizing; a photo with more texture is safer", UserWarning, stacklevel=2)
        return fallback
    raise ValueError("this image is too flat to carry a message (almost no texture, e.g. blank or one colour)")


def _reads(img, message, password):
    try:
        return reveal(img, password) == message
    except RevealError:
        return False


def reveal(image, password=None):
    """Return the hidden message bytes, or raise RevealError."""
    key = _key(password)
    img = _flatten(_open(image))[0].convert("RGB")
    fail = RevealError("no hidden message found (or wrong password)")
    if min(img.size) < core.GRID:
        raise fail
    soft = core.combine(core.cell_soft(np.asarray(img), key), NBITS)
    try:
        frame = rs.decode(np.packbits(soft > 0).tobytes(), NSYM)
    except ValueError:
        raise fail from None
    head, crc = frame[:-4], frame[-4:]
    version, mode, n = head[0] >> 4, head[0] & 15, head[1]
    if zlib.crc32(head).to_bytes(4, "big") != crc or version != VERSION or n > CAPACITY or mode > AES:
        raise fail
    if (mode == PLAIN) != (password is None):
        raise fail
    data = head[2:2 + n]
    if mode == PLAIN:
        return data
    if mode == XOR:
        if n < 8:
            raise fail
        return _xor(data[8:], key, data[:8])
    if AESGCM is None:
        raise RevealError("message is AES-encrypted: pip install stegsurvive[crypto]")
    if n < 28:
        raise fail
    try:
        return AESGCM(key).decrypt(data[:12], data[12:], None)
    except InvalidTag:
        raise RevealError("wrong password") from None
