"""Spread-transform QIM on luminance with a smooth, masked pattern.

A GRID x GRID canonical grid of chips is stretched over the image, so resizing keeps every chip
in place. Chips are grouped (keyed) into slots of CHIPS; a slot's value is the mean of its chips'
high-passed, Gaussian-averaged luma times a keyed +-1 sign, and carries one bit by dithered QIM.
Embedding moves each slot onto its bit's lattice with a band-limited pattern (Gaussian-upsampled
chips, high-passed: no cell edges, no slow blotches) whose amplitude follows local texture and
fades to 0 near black/white. QIM means the host image is not noise for the decoder, and reveal
needs only the stego image.
"""
import hashlib

import numpy as np

GRID = 128  # canonical chips per axis
CHIPS = 20  # chips per slot (one slot per coded bit): wide spread lets masking work
N_CELLS = GRID * GRID // CHIPS  # slots
DELTA = 1.0  # QIM step on a slot projection (spike-tuned: robustness vs visibility)
ITERS = 6  # correction passes: neighbouring chips overlap, clipping eats part of a step
RELAX = 0.6  # fraction of the remaining error corrected per pass (damps chip crosstalk)
SIGMA_HP = 0.8  # canonical px: Gaussian subtracted on both sides (high-pass)
SIGMA_UP = 0.6  # canonical px: chip-to-pixel smoothing (band limit, no cell edges)
STRENGTH = 0.5  # relative amplitude per unit of local luma std dev
AMP_MIN, AMP_MAX = 0.5, 6.0  # flat areas carry the least
MAX_CHANGE = 12.0  # luma levels: caps the push on thin dark strokes (text on white) to keep PSNR
TAPER = 24.0  # luma levels from 0/255 over which the change fades to 0
DEFAULT_KEY = b"stegsurvive-v1"


def stream(key: bytes, label: bytes, n: int) -> bytes:
    return hashlib.shake_256(key + label).digest(n)


def luma(rgb: np.ndarray, t=0) -> np.ndarray:
    """float32 HxW luma of rgb, or of clip(rgb + t) when a luma change t is applied to R, G and B."""
    y = np.zeros(rgb.shape[:2], np.float32)
    for c, k in enumerate((0.299, 0.587, 0.114)):
        y += k * np.clip(rgb[..., c].astype(np.float32) + t, 0, 255)
    return y


def _check(rgb: np.ndarray) -> None:
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("expected a uint8 HxWx3 RGB array")
    if min(rgb.shape[:2]) < GRID:
        raise ValueError(f"image too small: both sides must be >= {GRID} px")


def _gauss(rows: np.ndarray, sigma: float) -> np.ndarray:
    k = np.exp(-0.5 * ((rows[:, None] - np.arange(GRID)[None, :]) / sigma) ** 2)
    return k / k.sum(1, keepdims=True)


def _highpass(c: np.ndarray) -> np.ndarray:
    g = _gauss(np.arange(GRID, dtype=np.float64), SIGMA_HP)
    return c - g @ c @ g.T


def _up(n: int) -> np.ndarray:  # n x GRID: canonical grid -> pixels, smooth (float32: full-res math)
    return _gauss((np.arange(n) + 0.5) * GRID / n - 0.5, SIGMA_UP).astype(np.float32)


def _down(n: int) -> np.ndarray:  # GRID x n: Gaussian-weighted chip average (matched to _up)
    d = _up(n).T
    return d / d.sum(1, keepdims=True)


def _layout(key: bytes):
    used = N_CELLS * CHIPS  # chips left over when CHIPS does not divide GRID^2 stay unmarked
    perm = np.argsort(np.frombuffer(stream(key, b"perm", 4 * GRID * GRID), "<u4"), kind="stable")[:used]
    sign = (np.frombuffer(stream(key, b"sign", used), np.uint8) & 1) * 2.0 - 1
    dither = np.frombuffer(stream(key, b"dither", 2 * N_CELLS), "<u2") / 65536 * DELTA
    return perm, sign, dither


def _project(y: np.ndarray, down_h, down_w, perm, sign) -> np.ndarray:
    """Slot values: mean over each slot's chips of sign * high-passed canonical luma."""
    c = _highpass(down_h @ y @ down_w.T).ravel()[perm] * sign
    return c.reshape(N_CELLS, CHIPS).mean(1)


def _box(a: np.ndarray, r: int) -> np.ndarray:  # mean over a (2r+1)^2 window, edges reflected
    p = np.pad(a, r, mode="reflect").cumsum(0).cumsum(1)
    p = np.pad(p, ((1, 0), (1, 0)))
    n = 2 * r + 1
    return (p[n:, n:] - p[:-n, n:] - p[n:, :-n] + p[:-n, :-n]) / n ** 2


def _erode(a: np.ndarray, r: int) -> np.ndarray:  # min over a (2r+1)^2 window, separable
    win = np.lib.stride_tricks.sliding_window_view
    a = win(np.pad(a, ((r, r), (0, 0)), mode="edge"), 2 * r + 1, axis=0).min(-1)
    return win(np.pad(a, ((0, 0), (r, r)), mode="edge"), 2 * r + 1, axis=1).min(-1)


def mask(y: np.ndarray) -> np.ndarray:
    """Relative per-pixel amplitude: more in texture, less in flat areas, 0 at black/white.
    The texture measure is eroded so the flat side of a hard edge is not boosted (no halos)."""
    y = np.asarray(y, dtype=np.float64)  # cumulative sums need float64
    r = max(2, round(min(y.shape) / GRID))
    std = np.sqrt(np.maximum(_box(y * y, r) - _box(y, r) ** 2, 0))
    amp = np.clip(STRENGTH * _erode(std, 2 * r), AMP_MIN, AMP_MAX)
    return amp * np.clip(np.minimum(y, 255 - y) / TAPER, 0, 1)


def embed(rgb: np.ndarray, bits: np.ndarray, key: bytes) -> np.ndarray:
    """Spread-transform QIM: move each slot's projection onto its bit's lattice with a smooth,
    masked pattern (no cell edges), so the host image itself is not noise for the decoder."""
    _check(rgb)
    bits = np.asarray(bits)
    if bits.ndim != 1 or not 0 < bits.size <= N_CELLS or not np.isin(bits, (0, 1)).all():
        raise ValueError(f"bits must be 1..{N_CELLS} values of 0/1")
    h, w = rgb.shape[:2]
    perm, sign, dither = _layout(key)
    dh, dw, uh, uw = _down(h), _down(w), _up(h), _up(w)
    y = luma(rgb)
    m = mask(y)
    m32 = m.astype(np.float32)

    def change(slot_vals):  # slot values -> per-pixel luma change (float32)
        chips = np.zeros(GRID * GRID, np.float32)
        chips[perm] = sign * np.repeat(slot_vals, CHIPS)
        pattern = uh @ _highpass(chips.reshape(GRID, GRID)).astype(np.float32) @ uw.T
        pattern *= m32
        return pattern

    # gain of a slot onto itself: a lone chip's centre response (unit mask) x the mean mask there
    one = np.zeros((GRID, GRID))
    one[GRID // 2, GRID // 2] = 1
    k0 = _highpass(dh @ (uh @ _highpass(one).astype(np.float32) @ uw.T) @ dw.T)[GRID // 2, GRID // 2]
    mchip = (dh @ m @ dw.T).ravel()[perm].reshape(N_CELLS, CHIPS).mean(1)
    gain = k0 * mchip
    live = gain > k0 * AMP_MIN / 4  # slots lying mostly on black/white cannot move: leave them
    off = dither + bits[np.arange(N_CELLS) % bits.size] * DELTA / 2
    p = _project(y, dh, dw, perm, sign)
    target = np.round((p - off) / DELTA) * DELTA + off
    t = np.zeros((h, w), np.float32)  # luma change, applied equally to R, G, B
    for _ in range(ITERS):
        d = np.where(live, (target - _project(luma(rgb, t), dh, dw, perm, sign)) / np.maximum(gain, 1e-9), 0)
        t += RELAX * change(d)
        np.clip(t, -MAX_CHANGE, MAX_CHANGE, out=t)
    out = np.empty_like(rgb)
    for c in range(3):
        out[..., c] = np.clip(np.round(rgb[..., c] + t), 0, 255)
    return out


def cell_soft(rgb: np.ndarray, key: bytes) -> np.ndarray:
    """Per-slot soft bit in [-1, 1] in slot order (slot j carries bit j % K): > 0 means bit 1."""
    _check(rgb)
    h, w = rgb.shape[:2]
    perm, sign, dither = _layout(key)
    y = luma(rgb)
    dh, dw = _down(h), _down(w)
    p = _project(y, dh, dw, perm, sign)
    # slots on flat black/white could not be marked: weight them toward 0 (erasure), not noise
    live = np.clip((dh @ mask(y) @ dw.T).ravel()[perm].reshape(N_CELLS, CHIPS).mean(1) / AMP_MIN, 0, 1)
    return -np.cos(2 * np.pi * (p - dither) / DELTA) * live


def combine(soft: np.ndarray, k: int) -> np.ndarray:
    return np.bincount(np.arange(soft.size) % k, weights=soft, minlength=k)


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = np.mean((np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)) ** 2)
    return float("inf") if mse == 0 else float(10 * np.log10(255.0 ** 2 / mse))
