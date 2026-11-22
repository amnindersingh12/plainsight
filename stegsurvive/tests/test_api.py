import hashlib
import io
import unittest
import warnings
from unittest import mock

import numpy as np
from PIL import Image

import stegsurvive
from images import natural, plasma, scene, screenshot
from stegsurvive import AES_CAPACITY, CAPACITY, RevealError, core, hide, reveal, rs
from stegsurvive.attacks import ATTACKS, scale

MSG = hashlib.sha512(b"stegsurvive").digest()  # 64 bytes
A = {n: f for n, _, f in ATTACKS}


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = plasma(960, 720)
        cls.stego = hide(cls.img, MSG)

    def test_constants(self):
        self.assertEqual((CAPACITY, AES_CAPACITY), (64, 36))

    def test_required_attacks(self):
        for n, img in natural():
            stego = self.stego if n == "plasma" else hide(img, MSG)
            for name, req, fn in ATTACKS:
                if req:
                    with self.subTest(image=n, attack=name):
                        self.assertEqual(reveal(fn(stego)), MSG)

    def test_str_message(self):
        self.assertEqual(reveal(A["jpeg80"](hide(self.img, "héllo"))), "héllo".encode())

    def test_capacity(self):
        with self.assertRaisesRegex(ValueError, "64"):
            hide(self.img, bytes(65))

    def test_unmarked(self):
        with self.assertRaises(RevealError):
            reveal(self.img)

    def test_destroyed_image(self):
        with self.assertRaises(RevealError):
            reveal(scale(self.stego, 0.1))

    def test_xor_password(self):  # fallback without cryptography: warns, 8-byte nonce costs capacity
        with mock.patch("stegsurvive.AESGCM", None):
            m = MSG[:stegsurvive.XOR_CAPACITY]
            with self.assertWarnsRegex(UserWarning, "only obfuscates"):
                stego = hide(self.img, m, "pw")
            self.assertEqual(reveal(A["jpeg80"](stego), "pw"), m)
            with self.assertRaisesRegex(ValueError, "56"):
                hide(self.img, MSG[:57], "pw")

    def test_xor_keystream_not_reused(self):  # same password + message twice -> different ciphertext
        key = stegsurvive._key("pw")
        frames = []
        with mock.patch("stegsurvive.AESGCM", None), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for _ in range(2):
                soft = core.cell_soft(np.asarray(hide(self.img, b"same message", "pw")), key)
                frames.append(rs.decode(np.packbits(core.combine(soft, 816) > 0).tobytes()))
        self.assertNotEqual(frames[0], frames[1])

    def test_wrong_password(self):
        stego = hide(self.img, MSG[:AES_CAPACITY], "pw")
        with self.assertRaises(RevealError):
            reveal(stego, "nope")

    def test_missing_password(self):
        stego = hide(self.img, MSG[:AES_CAPACITY], "pw")
        with self.assertRaises(RevealError):
            reveal(stego)

    @unittest.skipUnless(stegsurvive.AESGCM, "needs cryptography")
    def test_aes(self):
        m = MSG[:36]
        stego = A["jpeg80"](hide(self.img, m, "pw"))
        self.assertEqual(reveal(stego, "pw"), m)
        with self.assertRaisesRegex(ValueError, "36"):
            hide(self.img, MSG[:37], "pw")
        from cryptography.exceptions import InvalidTag
        with mock.patch.object(stegsurvive.AESGCM, "decrypt", side_effect=InvalidTag):
            with self.assertRaisesRegex(RevealError, "wrong password"):
                reveal(stego, "pw")
        with mock.patch("stegsurvive.AESGCM", None):
            with self.assertRaisesRegex(RevealError, r"pip install stegsurvive\[crypto\]"):
                reveal(stego, "pw")

    def test_modes(self):
        # transparency: platforms flatten it (onto white here), so the mark must survive that
        rgba = self.img.convert("RGBA")
        alpha = np.tile(np.linspace(0, 255, 960).astype(np.uint8), (720, 1))
        alpha[:, :320] = 0  # fully transparent left third
        rgba.putalpha(Image.fromarray(alpha, "L"))
        with self.assertWarnsRegex(UserWarning, "flattened onto white"):
            out = hide(rgba, MSG)
        received = Image.new("RGBA", out.size, "white")
        received.alpha_composite(out.convert("RGBA"))
        self.assertEqual(reveal(A["jpeg80"](received)), MSG)
        for mode in ("L", "P"):
            with self.subTest(mode):
                out = hide(self.img.convert(mode), MSG)
                self.assertEqual(out.mode, "L" if mode == "L" else "RGB")  # P is not re-quantized
                self.assertEqual(reveal(A["jpeg80"](out)), MSG)

    def test_exif_orientation(self):
        buf = io.BytesIO()
        exif = Image.Exif()
        exif[0x0112] = 6
        self.img.save(buf, "JPEG", quality=95, exif=exif)
        buf.seek(0)
        stego = hide(Image.open(buf), MSG)
        self.assertEqual(stego.size, (720, 960))
        self.assertNotIn(0x0112, stego.getexif())
        self.assertEqual(reveal(A["jpeg80"](stego)), MSG)

    def test_odd_dimensions(self):
        self.assertEqual(reveal(A["resize75+jpeg80"](hide(scene(721, 1283), MSG))), MSG)

    def test_too_flat_is_refused(self):  # nothing can be embedded: must not report success
        for img in (Image.new("RGB", (960, 720), (250, 250, 250)), self.img.convert("1")):
            with self.subTest(img.mode):
                with self.assertRaisesRegex(ValueError, "too flat"):
                    hide(img, "hello")

    def test_size_limits(self):
        with self.assertRaisesRegex(ValueError, "256"):
            hide(plasma(200, 200), MSG)
        with self.assertWarns(UserWarning):
            hide(plasma(400, 400), MSG)

    def test_screenshot_psnr_stays_above_38(self):  # hard text edges must not buy reveal with PSNR
        img = screenshot(1280, 960)
        stego = hide(img, MSG)
        self.assertGreaterEqual(core.psnr(np.asarray(img), np.asarray(stego)), 38.0)

    def test_screenshot_measured(self):  # limitation: white backgrounds carry little; recorded only
        try:
            stego = hide(screenshot(960, 720), MSG)
        except ValueError as e:  # refused up front is fine; a silent bad embed is not
            self.assertIn("too flat", str(e))
            print("\nscreenshot 960x720: hide refused (too flat)")
            return
        try:
            ok = reveal(A["jpeg80"](stego)) == MSG
        except RevealError:
            ok = False
        print(f"\nscreenshot 960x720 jpeg80 reveal: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    unittest.main()
