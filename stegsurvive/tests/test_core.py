import unittest

import numpy as np

from images import natural, screenshot
from stegsurvive.attacks import ATTACKS, jpeg
from stegsurvive.core import DEFAULT_KEY, cell_soft, combine, embed, psnr

K = 816  # the 102-byte RS codeword x 8
KEY = DEFAULT_KEY
LIMIT = 8  # RS(102,70) fixes 16 bytes; 8 bit errors touch at most 8 bytes (2x margin)


def bits(seed):
    return np.random.default_rng(seed).integers(0, 2, K, dtype=np.uint8)


def arr(img):
    return np.asarray(img.convert("RGB"))


def errs(img, b, key=KEY):
    return int(((combine(cell_soft(arr(img), key), K) > 0) != b).sum())


def raw_ber(img, b, key=KEY):
    soft = cell_soft(arr(img), key)
    return float(((soft > 0) != b[np.arange(soft.size) % K]).mean())


class TestCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.stego = [(n, img, Image.fromarray(embed(arr(img), bits(i), KEY)), bits(i))
                     for i, (n, img) in enumerate(natural())]

    def test_clean_roundtrip(self):
        for n, _, s, b in self.stego:
            with self.subTest(n):
                self.assertEqual(errs(s, b), 0)
                self.assertLessEqual(raw_ber(s, b), 0.1)

    def test_psnr(self):
        for n, img, s, _ in self.stego:
            with self.subTest(n):
                self.assertGreaterEqual(psnr(arr(img), arr(s)), 38.0)

    def test_key_matters(self):
        for n, _, s, b in self.stego:
            with self.subTest(n):
                self.assertTrue(0.35 <= errs(s, b, b"other") / K <= 0.65)

    def test_white_background_measured(self):
        # Measured case, not a gate: pure white cannot be marked without visible darkening, so it
        # is left alone (PSNR stays high) and screenshots are a documented limitation.
        from PIL import Image
        img = screenshot(960, 720)
        s = embed(arr(img), bits(9), KEY)
        e = errs(jpeg(Image.fromarray(s), 80), bits(9))
        print(f"\nscreenshot PSNR {psnr(arr(img), s):.2f} dB, jpeg80 errs {e}/{K}")
        self.assertGreaterEqual(psnr(arr(img), s), 38.0)
        white = arr(img).min(-1) == 255
        self.assertTrue((s[white] >= 250).all())  # white stays white: no darkened background

    def test_embed_memory(self):  # 12 MP phone photos must not need > ~1 GB
        import tracemalloc
        from images import plasma
        a = arr(plasma(2000, 1500))
        tracemalloc.start()
        try:
            embed(a, bits(0), KEY)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak / a.shape[0] / a.shape[1], 80)  # bytes per pixel

    def test_go_no_go(self):
        from PIL import Image
        shot = screenshot(960, 720)
        cases = self.stego + [("screenshot", shot, Image.fromarray(embed(arr(shot), bits(9), KEY)), bits(9))]
        rows = []
        print()
        for n, img, s, b in cases:
            print(f"{n:<10} PSNR {psnr(arr(img), arr(s)):.2f} dB")
            for name, req, fn in ATTACKS:
                att = fn(s)
                row = (n, name, req, raw_ber(att, b), errs(att, b))
                rows.append(row)
                print(f"  {name:<16} {'required' if req else 'measured':<9} BER {row[3]:.4f}  errs {row[4]}/{K}")
        fails = [r for r in rows if r[0] != "screenshot" and r[2] and r[4] > LIMIT]
        self.assertEqual(fails, [])


if __name__ == "__main__":
    unittest.main()
