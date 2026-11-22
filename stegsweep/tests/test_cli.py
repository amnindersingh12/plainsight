import contextlib
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from fixtures import FLAG, make_jpeg_with_zip, make_png_lsb, make_png_text, make_wav_lsb, png_with_size

from stegsweep.cli import main


def out(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        p = patch("stegsweep.external.shutil.which", return_value=None)  # results must not depend on installed tools
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def test_png_lsb_end_to_end(self):
        d = self.d
        code, s = out([str(make_png_lsb(d)), "-o", str(d / "r")])
        self.assertEqual(code, 0)
        self.assertEqual(s.splitlines()[1], f"[100] lsb         bit0,rgb,xy,msbfirst: {FLAG}")
        html_ = (d / "r/index.html").read_text()
        self.assertIn(FLAG, html_)
        self.assertEqual(html_.count("<img "), 24)
        self.assertTrue((d / "r/lsb/bit0_rgb_xy_msbfirst.bin").exists())

    def test_jpeg_zip_end_to_end(self):
        d = self.d
        p, off, z = make_jpeg_with_zip(d)
        code, s = out([str(p), "-o", str(d / "r")])
        self.assertEqual(code, 0)
        self.assertIn(f"[100] strings     raw: {FLAG}", s)
        self.assertNotIn("txt" + FLAG, s)
        self.assertIn(f"[ 80] trailing    {len(z)} bytes after JPEG EOI at {off:#x} (zip data)", s)
        self.assertEqual((d / "r/trailing.bin").read_bytes(), z)
        self.assertTrue((d / f"r/carved/{off:08x}.zip").exists())

    def test_report_shows_only_this_runs_planes(self):
        d, r = self.d, self.d / "r"
        Image.new("RGBA", (8, 8)).save(d / "rgba.png")
        out([str(d / "rgba.png"), "-o", str(r)])
        out([str(make_png_text(d)), "-o", str(r)])
        h = (r / "index.html").read_text()
        self.assertEqual(h.count("<img "), 24)
        self.assertNotIn("planes/A0.png", h)

    def test_deflated_zip_after_png_ranked_first(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("flag.txt", FLAG * 3)
        p = self.d / "z.png"
        p.write_bytes(make_png_text(self.d, "nothing").read_bytes() + b.getvalue())
        self.assertEqual(out([str(p)])[1].splitlines()[1], f"[100] zip         zip:flag.txt: {FLAG}")

    def test_png_text_end_to_end(self):
        self.assertIn(f"[100] metadata    Comment: {FLAG}", out([str(make_png_text(self.d))])[1])

    def test_wav_end_to_end(self):
        self.assertIn(f"[100] wav-lsb     wav,bit0,msbfirst: {FLAG}", out([str(make_wav_lsb(self.d))])[1])

    def test_custom_flag_format(self):
        s = out([str(make_png_text(self.d, "secret{abc}")), "--flag-format", r"secret\{[^}]+\}"])[1]
        self.assertIn("[100] metadata    Comment: secret{abc}", s)

    def test_no_output_dir_writes_nothing(self):
        d = self.d
        p = make_png_lsb(d)
        before = sorted(os.listdir(d))
        cwd = os.getcwd()
        os.chdir(d)
        try:
            out([str(p)])
        finally:
            os.chdir(cwd)
        self.assertEqual(sorted(os.listdir(d)), before)

    def test_truncated_png_does_not_crash(self):
        p = self.d / "cut.png"
        p.write_bytes(make_png_lsb(self.d).read_bytes()[:100])
        code, s = out([str(p)])
        self.assertEqual(code, 0)
        self.assertIn("failed", s)

    def test_bomb_png_noted(self):
        p = self.d / "bomb.png"
        p.write_bytes(png_with_size(30000, 30000))
        code, s = out([str(p)])
        self.assertEqual(code, 0)
        self.assertIn("image too large: 30000x30000", s)

    def test_hostile_metadata_escaped(self):
        d = self.d
        code, s = out([str(make_png_text(d, "<script>alert(1)</script>\x1b[2J")), "-o", str(d / "r")])
        self.assertNotIn("\x1b", s)
        self.assertIn("\\x1b[2J", s)
        h = (d / "r/index.html").read_text()
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", h)
        self.assertNotIn("<script>alert", h)

    def test_bad_input(self):
        d = self.d
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(d / "missing.png")]), 2)
            with self.assertRaises(SystemExit) as cm:
                main([str(make_png_text(d)), "--flag-format", "("])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
