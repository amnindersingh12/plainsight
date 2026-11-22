import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from fixtures import jpeg_bytes, png_bytes

from stegsweep.core import DEFAULT_FLAG_FORMAT
from stegsweep.external import run_external

R = re.compile(DEFAULT_FLAG_FORMAT)
REAL_RUN = subprocess.run  # captured before the per-test patch replaces it


class ExternalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.jpg, self.png = self.d / "a.jpg", self.d / "a.png"
        self.jpg.write_bytes(jpeg_bytes())
        self.png.write_bytes(png_bytes())
        p = patch("stegsweep.external.subprocess.run")
        self.run = p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def only(self, tool):
        p = patch("stegsweep.external.shutil.which", side_effect=lambda t: f"/usr/bin/{t}" if t == tool else None)
        p.start()
        self.addCleanup(p.stop)

    def test_missing_tools_are_notes(self):
        with patch("stegsweep.external.shutil.which", return_value=None):
            fs = run_external(self.jpg, self.jpg.read_bytes(), "jpeg", None, Path("w.txt"), R)
        self.assertEqual({f.title for f in fs},
                         {f"{t} not installed, skipped" for t in ("exiftool", "binwalk", "steghide", "stegseek")})
        self.assertTrue(all(f.score == 0 for f in fs))
        self.run.assert_not_called()

    def test_exiftool_flag(self):
        self.only("exiftool")
        self.run.return_value = CompletedProcess([], 0, b"Comment : picoCTF{x}\n", b"")
        fs = run_external(self.jpg, self.jpg.read_bytes(), "jpeg", None, None, R)
        self.assertEqual(self.run.call_args.args[0], ["exiftool", "-a", "-u", "-g1", "-"])  # file on stdin
        self.assertEqual(self.run.call_args.kwargs["input"], self.jpg.read_bytes())
        self.assertIn(("exiftool: picoCTF{x}", 100), [(f.title, f.score) for f in fs])

    def test_stegseek_found(self):
        self.only("stegseek")

        def fake(args, **kw):
            Path(args[3]).write_bytes(b"hello")
            return CompletedProcess(args, 0, b'[i] Found passphrase: "hunter2"\n', b"")

        self.run.side_effect = fake
        [f] = [f for f in run_external(self.jpg, self.jpg.read_bytes(), "jpeg", None, Path("w.txt"), R) if f.check == "stegseek"]
        self.assertEqual((f.title, f.score, bytes(f.blob), f.name),
                         ('stegseek: passphrase "hunter2", extracted 5 bytes', 80, b"hello", "stegseek.out"))

    def test_steghide_not_run_for_png(self):
        self.only("steghide")
        run_external(self.png, self.png.read_bytes(), "png", None, None, R)
        self.run.assert_not_called()

    def test_timeout_is_note(self):
        self.only("exiftool")
        self.run.side_effect = subprocess.TimeoutExpired("exiftool", 120)
        self.assertIn("exiftool timed out after 120s", [f.title for f in run_external(self.jpg, self.jpg.read_bytes(), "jpeg", None, None, R)])

    def fake_tool(self, name, script):
        """Put a Python-script `name` alone on PATH and use the real subprocess.run."""
        self.run.side_effect = REAL_RUN
        bindir = self.d / "bin"
        bindir.mkdir(exist_ok=True)
        (bindir / name).write_text(f"#!{sys.executable} -I\nimport sys, os\n" + script)
        (bindir / name).chmod(0o755)
        p = patch.dict(os.environ, {"PATH": str(bindir)})
        p.start()
        self.addCleanup(p.stop)

    @unittest.skipIf(os.name != "posix", "shebang fake tools need POSIX")
    def test_binwalk_counts_only_new_files(self):
        self.fake_tool("binwalk", 'if sys.argv[1] == "--help": print("Binwalk v2.3.4"); sys.exit()\n'
                                  'd = os.path.join(sys.argv[3], "x.extracted"); os.makedirs(d, exist_ok=True)\n'
                                  'n = len(os.listdir(d))\n'
                                  'for k in "ab": open(os.path.join(d, k + str(n)), "w").close()\n')
        run_external(self.jpg, self.jpg.read_bytes(), "jpeg", self.d / "r", None, R)
        fs = run_external(self.jpg, self.jpg.read_bytes(), "jpeg", self.d / "r", None, R)
        self.assertIn("binwalk: extracted 2 files to binwalk/", [f.title for f in fs])

    @unittest.skipIf(os.name != "posix", "shebang fake tools need POSIX")
    def test_fake_exiftool_reads_stdin(self):
        self.fake_tool("exiftool", 'data = sys.stdin.buffer.read()\n'
                                   'print("Args : " + " ".join(sys.argv[1:])); print("Comment : flag{%d}" % len(data))\n')
        fs = run_external(self.jpg, self.jpg.read_bytes(), "jpeg", None, None, R)
        f = next(f for f in fs if f.check == "exiftool")
        self.assertEqual((f.title, f.score), (f"exiftool: flag{{{len(self.jpg.read_bytes())}}}", 100))
        self.assertIn("Args : -a -u -g1 -\n", f.detail)  # the path (CVE-2022-23935) never reaches exiftool
        self.assertIn("binwalk not installed, skipped", [f.title for f in fs])

    @unittest.skipIf(os.name != "posix", "shebang fake tools need POSIX")
    def test_old_or_unknown_binwalk_not_run(self):
        for banner, why in (("Binwalk v2.3.3", "version 2.3.3"), ("usage: binwalk", "unknown version")):
            self.fake_tool("binwalk", f'if sys.argv[1] == "--help": print({banner!r}); sys.exit()\n'
                                      'os.makedirs(sys.argv[3])\n')
            fs = run_external(self.jpg, self.jpg.read_bytes(), "jpeg", self.d / "r", None, R)
            self.assertIn(f"binwalk -e skipped: {why}, need >= 2.3.4 (CVE-2022-4510)", [f.title for f in fs])
            self.assertFalse((self.d / "r/binwalk").exists())

if __name__ == "__main__":
    unittest.main()
