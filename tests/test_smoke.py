# SPDX-License-Identifier: GPL-3.0-or-later
import re
import unittest
from pathlib import Path


class SmokeTest(unittest.TestCase):
    def test_version(self):
        import u2c_customfw
        self.assertEqual(u2c_customfw.__version__, "0.2.0")


ROOT = Path(__file__).parent.parent


class NameTest(unittest.TestCase):
    def test_the_app_is_called_firmware_toolkit(self):
        plist = (ROOT / "macos/Info.plist").read_text()
        self.assertIn("<key>CFBundleDisplayName</key><string>Firmware Toolkit</string>", plist)
        self.assertIn('window.title = "Firmware Toolkit"', (ROOT / "macos/main.swift").read_text())
        self.assertIn("<title>Firmware Toolkit</title>", (ROOT / "u2c_customfw/web/static/index.html").read_text())
        build = (ROOT / "macos/build.sh").read_text()
        self.assertIn('app="dist/Firmware Toolkit.app"', build)
        self.assertIn("firmware-toolkit-$version-macos-arm64.zip", build)
        self.assertIn("firmware-toolkit-$v-macos-arm64.zip", (ROOT / ".github/workflows/homebrew.yml").read_text())

    def test_the_identifiers_macos_and_the_backups_depend_on_stay(self):
        self.assertIn("<string>org.u2c-customfw.app</string>", (ROOT / "macos/Info.plist").read_text())
        self.assertIn('"u2c-customfw"', (ROOT / "u2c_customfw/state.py").read_text())


class DisclaimerTest(unittest.TestCase):
    def test_full_disclaimer_has_the_owners_wording(self):
        text = (ROOT / "DISCLAIMER.md").read_text()
        for phrase in ("tested on one controller, my own", "edge cases may exist", "I cannot know if it's possible for 8BitDo to tell",
                       "it won't let you continue", "the controller reports itself differently", "Not affiliated with or endorsed by 8BitDo"):
            self.assertIn(phrase, text)

    def test_readme_leads_with_the_app_and_a_short_warning(self):
        text = (ROOT / "README.md").read_text()
        self.assertTrue(text.startswith("# 8BitDo Ultimate 2C Firmware Toolkit"))
        self.assertNotIn("READ THIS FIRST", text)
        self.assertIn("no warranty", text[:text.index("## Install")].lower())
        self.assertIn("(DISCLAIMER.md)", text[:text.index("## Install")])
        self.assertIn("Not affiliated with or endorsed by 8BitDo", text)
        order = [text.index(h) for h in ("## What it does", "## Install", "## Use", "## Diagnostics", "## What the tweaks do", "## Credits", "## License")]
        self.assertEqual(order, sorted(order))


class MacBuildTest(unittest.TestCase):
    def test_the_app_is_built_for_the_macos_it_declares(self):
        minimum = re.search(r"LSMinimumSystemVersion</key><string>([\d.]+)", (ROOT / "macos/Info.plist").read_text()).group(1)
        self.assertIn(f"-target arm64-apple-macos{minimum}", (ROOT / "macos/build.sh").read_text())


if __name__ == "__main__":
    unittest.main()
