import contextlib
import io
import os
import struct
import tempfile
import unittest
import zlib
from unittest import mock

from images import plasma
from stegsurvive.attacks import ATTACKS
from stegsurvive.cli import main


def png_header(w, h):  # header-only PNG claiming w x h pixels (never decoded)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IEND", b"")


class TestCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.inp = os.path.join(cls.tmp.name, "in.png")
        plasma(960, 720).save(cls.inp)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def test_hide_reveal_png(self):
        code, out, _ = self.run_cli("hide", self.inp, "hello world", "-o", self.path("out.png"))
        self.assertEqual(code, 0)
        self.assertIn("PSNR", out)
        code, out, err = self.run_cli("reveal", self.path("out.png"))
        self.assertEqual((code, out), (0, "hello world\n"))
        self.assertIn("PASS", err)

    def test_hide_to_jpeg(self):
        self.assertEqual(self.run_cli("hide", self.inp, "hello world", "-o", self.path("out.jpg"))[0], 0)
        code, out, _ = self.run_cli("reveal", self.path("out.jpg"))
        self.assertEqual((code, out), (0, "hello world\n"))

    def test_reveal_fail(self):
        code, _, err = self.run_cli("reveal", self.inp)
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("FAIL"))

    def test_password_prompt(self):
        with mock.patch("getpass.getpass", return_value="pw"):
            self.assertEqual(self.run_cli("hide", self.inp, "secret", "-o", self.path("pw.png"),
                                          "--password")[0], 0)
            self.assertEqual(self.run_cli("reveal", self.path("pw.png"), "--password")[:2], (0, "secret\n"))
        self.assertEqual(self.run_cli("reveal", self.path("pw.png"))[0], 1)

    def test_password_fallback_warns(self):
        with mock.patch("getpass.getpass", return_value="pw"), mock.patch("stegsurvive.AESGCM", None):
            code, _, err = self.run_cli("hide", self.inp, "secret", "-o", self.path("x.png"), "--password")
        self.assertEqual(code, 0)
        self.assertIn("warning: ", err)
        self.assertIn("only obfuscates", err)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            main(["hide", "-h"])
        self.assertIn("obfuscation", buf.getvalue())

    def test_too_long(self):
        code, _, err = self.run_cli("hide", self.inp, "x" * 65, "-o", self.path("long.png"))
        self.assertEqual(code, 2)
        self.assertIn("64", err)
        self.assertFalse(os.path.exists(self.path("long.png")))

    def test_flat_image_refused(self):
        from PIL import Image
        Image.new("RGB", (960, 720), (250, 250, 250)).save(self.path("flat.png"))
        code, out, err = self.run_cli("hide", self.path("flat.png"), "hello", "-o", self.path("flat_out.png"))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("too flat", err)

    def test_huge_images_refused(self):
        for name, (w, h) in (("56mp.png", (8000, 7000)), ("196mp.png", (14000, 14000))):
            with open(self.path(name), "wb") as f:
                f.write(png_header(w, h))
            for cmd in (["hide", self.path(name), "hi", "-o", self.path("o.png")], ["reveal", self.path(name)],
                        ["bench", self.path(name)]):
                with self.subTest(name=name, cmd=cmd[0]):
                    code, _, err = self.run_cli(*cmd)
                    self.assertEqual(code, 2)
                    self.assertTrue(err.startswith("error:"), err)
                    self.assertIn("50 MP" if name == "56mp.png" else "decompression bomb", err)

    def test_missing_file(self):
        code, _, err = self.run_cli("reveal", self.path("nope.png"))
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error:"))

    def test_not_an_image(self):
        with open(self.path("junk.png"), "wb") as f:
            f.write(b"not an image")
        code, _, err = self.run_cli("reveal", self.path("junk.png"))
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error:"))

    def test_bench(self):
        code, out, _ = self.run_cli("bench", self.inp)
        self.assertEqual(code, 0)
        self.assertIn("PSNR", out)
        for name, _, _ in ATTACKS:
            self.assertIn(name, out)


if __name__ == "__main__":
    unittest.main()
