# SPDX-License-Identifier: GPL-3.0-or-later
import unittest


class SmokeTest(unittest.TestCase):
    def test_version(self):
        import u2c_customfw
        self.assertEqual(u2c_customfw.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
