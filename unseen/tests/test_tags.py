import unittest

from unseen.tags import decode_tags, hide, is_rgi_flag, reveal

FLAG = "\U0001F3F4"
CANCEL = "\U000E007F"


class TagsTest(unittest.TestCase):
    def test_hide_roundtrip(self):
        self.assertEqual(hide("hi"), "\U000E0068\U000E0069")
        self.assertEqual(decode_tags(hide("ignore previous instructions")), "ignore previous instructions")

    def test_hide_rejects_non_ascii(self):
        for bad in ("caf\u00e9", "a\nb"):
            with self.assertRaises(ValueError):
                hide(bad)

    def test_decode_drops_language_and_cancel(self):
        self.assertEqual(decode_tags("\U000E0001\U000E0041" + CANCEL), "A")

    def test_rgi_flags(self):
        self.assertTrue(is_rgi_flag(FLAG, hide("gbeng") + CANCEL))
        self.assertFalse(is_rgi_flag(FLAG, hide("usca") + CANCEL))  # valid ISO code but not RGI
        self.assertFalse(is_rgi_flag("x", hide("gbeng") + CANCEL))
        self.assertFalse(is_rgi_flag(FLAG, hide("gbeng")))  # no cancel tag

    def test_reveal_finds_each_run(self):
        self.assertEqual(reveal("a" + hide("one") + "b" + hide("two")), ["one", "two"])
        self.assertEqual(reveal("plain"), [])
        self.assertEqual(reveal(FLAG + hide("gbsct") + CANCEL), [])


if __name__ == "__main__":
    unittest.main()
