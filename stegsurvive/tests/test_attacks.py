import unittest

import numpy as np

from images import plasma, scene
from stegsurvive.attacks import ATTACKS, jpeg


class TestAttacks(unittest.TestCase):
    def test_names(self):
        req = [n for n, r, _ in ATTACKS if r]
        meas = [n for n, r, _ in ATTACKS if not r]
        self.assertEqual(req, ["jpeg95", "jpeg90", "jpeg80", "jpeg70", "jpeg60", "resize75+jpeg80",
                               "resize50+jpeg80", "webp80", "whatsapp", "telegram", "x", "instagram", "facebook"])
        self.assertEqual(meas, ["jpeg50", "crop5"])

    def test_sizes(self):
        a = {n: f for n, _, f in ATTACKS}
        p = plasma(960, 720)
        s = scene(720, 1280)
        self.assertEqual(a["resize50+jpeg80"](p).size, (480, 360))
        self.assertEqual(a["resize75+jpeg80"](p).size, (720, 540))
        self.assertEqual(a["instagram"](s).size, (608, 1080))
        self.assertEqual(a["x"](p).size, (960, 720))
        self.assertEqual(a["crop5"](p).size, (912, 684))
        self.assertTrue(all(f(p).mode == "RGB" for _, _, f in ATTACKS))

    def test_jpeg_is_lossy(self):
        x = np.asarray(plasma(960, 720), float)
        y = np.asarray(jpeg(plasma(960, 720), 60), float)
        d = np.abs(x - y).mean()
        self.assertGreater(d, 0.1)
        self.assertLess(d, 10)


if __name__ == "__main__":
    unittest.main()
