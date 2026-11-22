import re
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from fixtures import jpeg_bytes, make_jpeg_with_zip, make_png_lsb, make_wav_lsb, png_with_size
from PIL import Image

from stegsweep.core import (DEFAULT_FLAG_FORMAT, Finding, clean, find_flags, open_image, printable_runs, rank,
                            save_artifact, sniff)

R = re.compile(DEFAULT_FLAG_FORMAT)


class CoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_find_flags_default(self):
        self.assertEqual(find_flags(b"xx picoCTF{abc} yy flag{d_e} \x00HTB{z} picoCTF{abc}", R),
                         ["picoCTF{abc}", "flag{d_e}", "HTB{z}"])

    def test_find_flags_trims_glued_prefix(self):
        self.assertEqual(find_flags(b"flag.txtpicoCTF{x} flag.txtflag{h} xyzctf{g} DUCTF{d}", R),
                         ["picoCTF{x}", "flag{h}", "xyzctf{g}", "DUCTF{d}"])
        self.assertEqual(find_flags(b"txtpicoCTF{x}", re.compile(r"\w+CTF\{[^}]+\}")), ["txtpicoCTF{x}"])

    def test_find_flags_cap(self):
        self.assertEqual(len(find_flags(b" ".join(b"flag{%d}" % i for i in range(50)), R)), 20)

    def test_printable_runs(self):
        self.assertEqual(list(printable_runs(b"\x00hello world\x01ab\x02longer_string!", 6)),
                         ["hello world", "longer_string!"])

    def test_clean(self):
        self.assertEqual(clean("a\x1b[31m\nb"), "a\\x1b[31m\\x0ab")
        self.assertEqual(clean("x" * 200, 10), "x" * 10 + "...")
        self.assertEqual(clean("a\u202eb"), "a\\u202eb")

    def test_sniff(self):
        self.assertEqual(sniff(b"\x89PNG\r\n\x1a\n" + b"\0" * 8), "png")
        self.assertEqual(sniff(b"\xff\xd8\xff\xe0"), "jpeg")
        self.assertEqual(sniff(b"GIF89a"), "gif")
        self.assertEqual(sniff(b"GIF87a"), "gif")
        self.assertEqual(sniff(b"BM\0\0\0\0"), "bmp")
        self.assertEqual(sniff(b"II*\0"), "tiff")
        self.assertEqual(sniff(b"MM\0*"), "tiff")
        self.assertEqual(sniff(b"RIFF\0\0\0\0WEBPVP8 "), "webp")
        self.assertEqual(sniff(b"RIFF\0\0\0\0WAVEfmt "), "wav")
        self.assertEqual(sniff(b"hello"), "other")

    def test_rank(self):
        fs = [Finding("strings", "a", 10), Finding("lsb", "b", 100), Finding("trailing", "c", 80),
              Finding("lsb", "b", 100)]
        self.assertEqual([f.score for f in rank(fs)], [100, 80, 10])

    def test_open_image_rejects_bomb(self):
        with self.assertRaisesRegex(ValueError, "image too large: 30000x30000"):
            open_image(png_with_size(30000, 30000))

    def test_save_artifact(self):
        d = self.d
        self.assertEqual(save_artifact(d, "lsb/x.bin", memoryview(b"abc")).read_bytes(), b"abc")
        for bad in ("../evil", "/tmp/evil", "a/../../evil"):
            with self.assertRaises(ValueError):
                save_artifact(d, bad, b"")
        (d / "link").symlink_to(d.parent)
        with self.assertRaises(ValueError):
            save_artifact(d, "link/evil", b"")

    def test_fixtures_valid(self):
        d = self.d
        with Image.open(make_png_lsb(d)) as img:
            self.assertEqual((img.mode, img.size), ("RGB", (64, 64)))
        with wave.open(str(make_wav_lsb(d))) as w:
            self.assertEqual((w.getnframes(), w.getsampwidth()), (4000, 2))
        path, off, _ = make_jpeg_with_zip(d)
        self.assertEqual(zipfile.ZipFile(path).namelist(), ["flag.txt"])
        self.assertEqual(off, len(jpeg_bytes()))


if __name__ == "__main__":
    unittest.main()
