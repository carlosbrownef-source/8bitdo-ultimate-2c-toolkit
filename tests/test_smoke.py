# SPDX-License-Identifier: GPL-3.0-or-later
import re
import unittest
from pathlib import Path


class SmokeTest(unittest.TestCase):
    def test_version(self):
        import u2c_customfw
        self.assertEqual(u2c_customfw.__version__, "0.1.1")


class MacBuildTest(unittest.TestCase):
    def test_the_app_is_built_for_the_macos_it_declares(self):
        root = Path(__file__).parent.parent
        minimum = re.search(r"LSMinimumSystemVersion</key><string>([\d.]+)", (root / "macos/Info.plist").read_text()).group(1)
        self.assertIn(f"-target arm64-apple-macos{minimum}", (root / "macos/build.sh").read_text())


if __name__ == "__main__":
    unittest.main()
