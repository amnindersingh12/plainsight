import random
import unittest

from stegsurvive.rs import decode, encode


def corrupt(code, e, rng):
    c = bytearray(code)
    for i in rng.sample(range(len(c)), e):
        c[i] ^= rng.randrange(1, 256)
    return bytes(c)


class TestRS(unittest.TestCase):
    def test_known_vector(self):  # reedsolo README example, nsym=10
        self.assertEqual(encode(b"hello world", 10), b"hello world\xed%T\xc4\xfd\xfd\x89\xf3\xa8\xaa")

    def test_systematic(self):
        c = encode(b"hello")
        self.assertEqual(c[:5], b"hello")
        self.assertEqual(len(c), 37)

    def test_corrects_up_to_16(self):
        rng = random.Random(0)
        for trial in range(200):
            data = bytes(rng.randrange(256) for _ in range(70))
            self.assertEqual(decode(corrupt(encode(data), trial % 17, rng)), data)

    def test_too_many_errors_raises(self):
        rng = random.Random(1)
        for trial in range(200):
            data = bytes(rng.randrange(256) for _ in range(70))
            with self.assertRaises(ValueError):
                decode(corrupt(encode(data), rng.randint(17, 40), rng))

    def test_length_limit(self):
        with self.assertRaises(ValueError):
            encode(bytes(224), 32)


if __name__ == "__main__":
    unittest.main()
