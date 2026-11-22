import io
import re
import tempfile
import unittest
import wave
from pathlib import Path

from fixtures import FLAG, make_png_lsb, make_wav_lsb
from PIL import Image

from stegsweep.core import DEFAULT_FLAG_FORMAT, SIGNATURES
from stegsweep.lsb import channel_orders, save_bit_planes, sweep_image, sweep_wav

R = re.compile(DEFAULT_FLAG_FORMAT)


class LsbTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_channel_orders(self):
        self.assertEqual(channel_orders(("R", "G", "B")), ["r", "g", "b", "rgb", "bgr"])
        self.assertEqual(channel_orders(("R", "G", "B", "A")), ["r", "g", "b", "a", "rgb", "bgr", "rgba", "abgr"])
        self.assertEqual(channel_orders(("L",)), ["l"])
        self.assertEqual(channel_orders(("L", "A")), ["l", "a", "la", "al"])

    def test_png_lsb_flag(self):
        fs = sweep_image(Image.open(make_png_lsb(self.d)), R)
        self.assertEqual([f.title for f in fs if f.score == 100], [f"bit0,rgb,xy,msbfirst: {FLAG}"])
        f = next(f for f in fs if f.score == 100)
        self.assertEqual(f.name, "lsb/bit0_rgb_xy_msbfirst.bin")
        self.assertTrue(bytes(f.blob).startswith(FLAG.encode()))

    def test_two_bit_lsb(self):  # zsteg b2: bits 1 and 0 of each channel value, in that order
        bits = [(c >> (7 - i)) & 1 for c in FLAG.encode() + b"\0" for i in range(8)]
        img = Image.new("RGB", (64, 64), (100, 150, 200))
        flat = bytearray(img.tobytes())
        for i in range(0, len(bits), 2):
            flat[i // 2] = (flat[i // 2] & ~3) | (bits[i] << 1) | bits[i + 1]
        img.frombytes(bytes(flat))
        self.assertEqual([f.title for f in sweep_image(img, R) if f.score == 100], [f"bit0-1,rgb,xy,msbfirst: {FLAG}"])

    def test_lsb_hidden_file(self):
        fs = sweep_image(Image.open(make_png_lsb(self.d, SIGNATURES["zip"] + b"\0" * 20)), R)
        self.assertIn("bit0,rgb,xy,msbfirst: zip file", [f.title for f in fs])

    def test_no_findings_on_plain_image(self):
        self.assertEqual([f for f in sweep_image(Image.new("RGB", (64, 64), (10, 20, 30)), R) if f.score >= 50], [])

    def test_wav_lsb_flag(self):
        fs = sweep_wav(make_wav_lsb(self.d).read_bytes(), R)
        self.assertEqual([f.title for f in fs if f.score == 100], [f"wav,bit0,msbfirst: {FLAG}"])

    def test_wav_unsupported_width(self):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(3)
            w.setframerate(8000)
            w.writeframes(b"\0" * 300)
        self.assertEqual([f.title for f in sweep_wav(buf.getvalue(), R)], ["unsupported sample width 3"])

    def test_bit_planes(self):
        d = self.d
        paths = save_bit_planes(Image.open(make_png_lsb(d)), d / "planes")
        self.assertEqual(len(paths), 24)
        self.assertEqual(paths[0].name, "R0.png")
        self.assertEqual(Image.open(d / "planes/R0.png").getpixel((0, 0)), 0)  # 'p' = 0b01110000: first bit 0
        self.assertEqual(Image.open(d / "planes/G0.png").getpixel((0, 0)), 255)  # second bit 1

    def test_modes_do_not_crash(self):
        for mode in ("P", "L", "LA", "RGBA", "1", "I;16"):
            img = Image.new(mode, (20, 20))
            self.assertIsInstance(sweep_image(img, R), list)
            self.assertTrue(save_bit_planes(img, self.d / mode))


if __name__ == "__main__":
    unittest.main()
