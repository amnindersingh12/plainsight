import io
import re
import struct
import tempfile
import time
import tracemalloc
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

from fixtures import FLAG, insert_before_iend, jpeg_bytes, make_jpeg_with_zip, make_png_text, png_bytes, png_chunk

from PIL import Image

from stegsweep.checks import check_metadata, check_zip_members, check_png_chunks, check_signatures, check_strings, check_trailing
from stegsweep.core import DEFAULT_FLAG_FORMAT, SIGNATURES

R = re.compile(DEFAULT_FLAG_FORMAT)


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_metadata_png_text(self):
        fs = check_metadata(make_png_text(self.d).read_bytes(), R)
        self.assertIn(("Comment: " + FLAG, 100), [(f.title, f.score) for f in fs])
        self.assertIn(("Author: alice", 50), [(f.title, f.score) for f in fs])

    def test_metadata_ztxt_after_idat(self):
        z = png_chunk(b"zTXt", b"Comment\0\0" + zlib.compress(FLAG.encode()))
        fs = check_metadata(insert_before_iend(png_bytes(), z), R)
        self.assertIn(("Comment: " + FLAG, 100), [(f.title, f.score) for f in fs])

    def test_metadata_exif_text_encodings(self):
        def jpeg_with(exif):
            b = io.BytesIO()
            Image.new("RGB", (16, 16)).save(b, "JPEG", exif=exif.tobytes())
            return b.getvalue()

        xp = Image.Exif()
        xp[0x9C9C] = FLAG.encode("utf-16le") + b"\0\0"  # XPComment
        uc = Image.Exif()
        uc.get_ifd(0x8769)[0x9286] = b"UNICODE\0" + FLAG.encode("utf-16be")  # UserComment
        for name, exif in (("XPComment", xp), ("UserComment", uc)):
            fs = check_metadata(jpeg_with(exif), R)
            self.assertIn((f"EXIF {name}: {FLAG}", 100), [(f.title, f.score) for f in fs], name)

    def test_metadata_jpeg_comment(self):
        fs = check_metadata(jpeg_bytes(comment=b"hello comment"), R)
        self.assertIn(("comment: hello comment", 50), [(f.title, f.score) for f in fs])

    def test_trailing_jpeg_zip(self):
        path, off, z = make_jpeg_with_zip(self.d)
        [f] = check_trailing(path.read_bytes())
        self.assertEqual(f.title, f"{len(z)} bytes after JPEG EOI at {off:#x} (zip data)")
        self.assertEqual((f.score, f.name, bytes(f.blob)), (80, "trailing.bin", z))

    def test_trailing_ignores_thumbnail(self):
        thumb, main = jpeg_bytes((8, 8)), jpeg_bytes()
        data = main[:2] + b"\xff\xe1" + struct.pack(">H", len(thumb) + 2) + thumb + main[2:]
        self.assertEqual(check_trailing(data), [])

    def test_trailing_jpeg_fill_and_stuffing_fast(self):
        # a per-byte Python walk takes ~3 s on 20 MiB here; the C-level scan takes milliseconds
        for data in (b"\xff\xd8" + b"\xff" * 20 * 2**20, b"\xff\xd8\xff\xda\x00\x02" + b"\xff\x00" * 10 * 2**20):
            t = time.monotonic()
            self.assertEqual(check_trailing(data), [])
            self.assertLess(time.monotonic() - t, 1)

    def test_trailing_png(self):
        png = png_bytes()
        [f] = check_trailing(png + b"hidden")
        self.assertEqual((f.title, bytes(f.blob)), (f"6 bytes after PNG IEND at {len(png):#x}", b"hidden"))

    def test_signatures_jpeg_zip(self):
        path, off, _ = make_jpeg_with_zip(self.d)
        fs = check_signatures(path.read_bytes())
        self.assertEqual([(f.title, f.name) for f in fs], [(f"zip at {off:#x}", f"carved/{off:08x}.zip")])

    def test_signatures_cut_at_next_hit(self):
        png = png_bytes()
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_STORED) as z:
            z.writestr("a.png", png)
            z.writestr("flag.txt", FLAG)
        zdata = b.getvalue()
        fs = check_signatures(b"\0" + zdata + b"junk" * 100)
        self.assertEqual([f.title.split()[0] for f in fs], ["zip", "png", "zip"])
        self.assertEqual(bytes(fs[0].blob), zdata)  # a zip ends at its end-of-central-directory record
        self.assertEqual(bytes(fs[1].blob), png)  # anything else ends at the next signature

    def test_signatures_budget(self):
        data = b"\0" + (SIGNATURES["pdf"] + b"x" * 45) * 3
        with patch("stegsweep.checks.CARVE_BUDGET", 100):
            fs = check_signatures(data)
        self.assertEqual([(f.score, len(f.blob or b"")) for f in fs], [(80, 50), (80, 50), (0, 0)])
        self.assertEqual(fs[2].title, "carving stopped at 0x65: 100-byte budget used")

    def deflated_zip(self, members):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            for name, body in members:
                z.writestr(name, body)
        return b.getvalue()

    def test_zip_member_flag(self):
        fs = check_zip_members(png_bytes() + self.deflated_zip([("flag.txt", FLAG * 3)]), R)
        self.assertIn((f"zip:flag.txt: {FLAG}", 100), [(f.title, f.score) for f in fs])
        member = next(f for f in fs if f.blob is not None)
        self.assertEqual((bytes(member.blob), member.name), ((FLAG * 3).encode(), f"zip/{len(png_bytes()):08x}_0000.bin"))

    def test_zip_encrypted_member(self):
        z = bytearray(self.deflated_zip([("secret.txt", FLAG)]))
        z[6] |= 1  # local header: encrypted bit
        z[z.index(b"PK\x01\x02") + 8] |= 1  # central directory: encrypted bit
        fs = check_zip_members(b"\0" + bytes(z), R)
        self.assertEqual([(f.title, f.score) for f in fs],
                         [("encrypted zip member secret.txt (try a wordlist: zip2john / fcrackzip)", 40)])

    def test_zip_bomb_capped(self):
        z = self.deflated_zip([("bomb.bin", b"\0" * 64 * 2**20)])
        tracemalloc.start()
        try:
            with patch("stegsweep.checks.ZIP_MEMBER_CAP", 2**20):
                fs = check_zip_members(b"\0" + z, R)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertEqual([f.title for f in fs], ["zip:bomb.bin: 1048576 bytes (capped)"])
        self.assertLess(peak, 8 * 2**20)
        lie = bytearray(z)  # central directory declares 10 bytes: reading must stay bounded and not crash
        struct.pack_into("<I", lie, lie.index(b"PK\x01\x02") + 24, 10)
        fs = check_zip_members(b"\0" + bytes(lie), R)
        self.assertTrue(all(len(f.blob or b"") <= 10 for f in fs))

    def test_strings_flag(self):
        fs = check_strings(b"\0" * 10 + b"picoCTF{raw}" + b"\x01", R)
        self.assertEqual([(f.title, f.score) for f in fs],
                         [("raw: picoCTF{raw}", 100), ("1 printable strings (8+ chars)", 10)])

    def test_strings_streams_runs(self):
        data = b"aaaaaaaa\0" * 300_000
        tracemalloc.start()
        try:
            [f] = check_strings(data, R)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertEqual(f.title, "300000 printable strings (8+ chars)")
        self.assertEqual(len(f.detail.splitlines()), 2000)
        self.assertLess(peak, len(data) + 2 * 2**20)  # one decoded copy for the flag search; a list of runs is ~30 MiB

    def test_png_chunks_clean(self):
        self.assertEqual(check_png_chunks(make_png_text(self.d).read_bytes()), [])

    def test_png_chunks_bad_crc(self):
        png = bytearray(png_bytes())
        png[22] ^= 0xFF  # IHDR height byte, CRC left stale
        [f] = check_png_chunks(bytes(png))
        self.assertEqual((f.check, f.score), ("png-chunks", 40))
        self.assertTrue(f.title.startswith("IHDR CRC mismatch"))

    def test_png_chunks_unknown(self):
        [f] = check_png_chunks(insert_before_iend(png_bytes(), png_chunk(b"flAg", FLAG.encode())))
        self.assertEqual(f.title, f"unknown chunk 'flAg' ({len(FLAG)} bytes)")
        self.assertEqual(bytes(f.blob), FLAG.encode())
        self.assertRegex(f.name, r"^chunks/[0-9a-f]{8}_flAg\.bin$")

    def test_png_chunks_truncated(self):
        [f] = check_png_chunks(png_bytes()[:40])
        self.assertTrue(f.title.startswith("truncated chunk at"))


if __name__ == "__main__":
    unittest.main()
