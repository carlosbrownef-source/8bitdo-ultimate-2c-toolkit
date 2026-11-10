# SPDX-License-Identifier: GPL-3.0-or-later
import re
import unittest
from pathlib import Path


class SmokeTest(unittest.TestCase):
    def test_version(self):
        import u2c_customfw
        self.assertEqual(u2c_customfw.__version__, "1.0.1b1")


ROOT = Path(__file__).parent.parent


class NameTest(unittest.TestCase):
    def test_the_app_is_called_u2c_firmware_toolkit_inside_and_keeps_its_file_names(self):
        plist = (ROOT / "macos/Info.plist").read_text()
        self.assertIn("<key>CFBundleName</key><string>U2C Firmware Toolkit</string>", plist)
        self.assertIn("<key>CFBundleDisplayName</key><string>U2C Firmware Toolkit</string>", plist)
        swift = (ROOT / "macos/main.swift").read_text()
        self.assertIn('window.title = "U2C Firmware Toolkit"', swift)
        self.assertIn('"Quit U2C Firmware Toolkit"', swift)
        page = (ROOT / "u2c_customfw/web/static/index.html").read_text()
        self.assertIn("<title>U2C Firmware Toolkit</title>", page)
        self.assertIn("<b>U2C Firmware Toolkit</b>", page)
        build = (ROOT / "macos/build.sh").read_text()
        self.assertIn('app="$out/Firmware Toolkit.app"', build)
        self.assertIn("firmware-toolkit-$version-macos-$arch.zip", build)
        self.assertIn("firmware-toolkit-$v-macos-$arch.zip", (ROOT / ".github/workflows/homebrew.yml").read_text())
        self.assertIn("for arch in arm64 x86_64", (ROOT / ".github/workflows/homebrew.yml").read_text())

    def test_homebrew_uses_the_new_name(self):
        workflow = (ROOT / ".github/workflows/homebrew.yml").read_text()
        self.assertIn("Formula/firmware-toolkit.rb", workflow)
        self.assertIn("Casks/firmware-toolkit.rb", workflow)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("carlosbrownef-source/tap/firmware-toolkit", readme)
        self.assertNotIn("tap/u2c-customfw", readme)

    def test_the_identifiers_macos_and_the_backups_depend_on_stay(self):
        self.assertIn("<string>org.u2c-customfw.app</string>", (ROOT / "macos/Info.plist").read_text())
        self.assertIn('"u2c-customfw"', (ROOT / "u2c_customfw/state.py").read_text())


class DisclaimerTest(unittest.TestCase):
    def test_full_disclaimer_has_the_owners_wording(self):
        text = (ROOT / "DISCLAIMER.md").read_text()
        for phrase in ("tested on one controller and one dongle, my own", "edge cases may exist", "I cannot know if it's possible for 8BitDo to tell",
                       "it won't let you continue", "the controller and the dongle report themselves differently", "Not affiliated with or endorsed by 8BitDo"):
            self.assertIn(phrase, text)
        self.assertTrue(text.startswith("# Before you start\n"))

    def test_readme_gives_credit_to_the_other_projects(self):
        text = (ROOT / "README.md").read_text()
        for project in ("lodo4nik/8bitdo-sdl-macos-fix", "amirreza225/8bitdo-ultimate-2c-mac", "MoridaDE/8bitdo-2c-battery-tray"):
            self.assertIn(project, text)
        self.assertIn("MoridaDE/8bitdo-2c-battery-tray", (ROOT / "CREDITS.md").read_text())

    def test_readme_leads_with_the_app_and_a_short_warning(self):
        text = (ROOT / "README.md").read_text()
        self.assertTrue(text.startswith("# U2C Firmware Toolkit"))
        self.assertNotIn("READ THIS FIRST", text)
        self.assertIn("no warranty", text[:text.index("## Install")].lower())
        self.assertIn("written with an AI assistant (Opus 5.5)", text[:text.index("## Install")])
        self.assertIn("(DISCLAIMER.md)", text[:text.index("## Install")])
        self.assertIn("Not affiliated with or endorsed by 8BitDo", text)
        self.assertIn("(SAFEGUARDS.md)", text[:text.index("## Install")])
        order = [text.index(h) for h in ("## What it does", "## Install", "## Use", "## Documentation", "## Credits", "## License")]
        self.assertEqual(order, sorted(order))

    def test_one_warranty_sentence(self):
        self.assertIn("Installing modified firmware probably voids the controller's and the dongle's warranty.", (ROOT / "README.md").read_text())
        disclaimer = (ROOT / "DISCLAIMER.md").read_text()
        self.assertIn("**Installing it probably voids your controller's and dongle's warranty.**", disclaimer)
        self.assertIn("makes a lot of assumptions", disclaimer)
        for path in ("README.md", "DISCLAIMER.md", "u2c_customfw/cli.py", "u2c_customfw/disclaimer.py", "u2c_customfw/web/static/index.html", "u2c_customfw/web/static/app.js"):
            text = (ROOT / path).read_text()
            for old in ("lose your controller's warranty", "voids its warranty", "voids the warranty", "this voids", "Changing the firmware voids"):
                self.assertNotIn(old, text, path)


class MacBuildTest(unittest.TestCase):
    def test_the_app_is_built_for_the_macos_it_declares(self):
        minimum = re.search(r"LSMinimumSystemVersion</key><string>([\d.]+)", (ROOT / "macos/Info.plist").read_text()).group(1)
        script = (ROOT / "macos/build.sh").read_text()
        self.assertIn(f'-target "$arch-apple-macos{minimum}"', script)
        for arch in ("arm64)", "x86_64)"):   # Apple silicon and Intel, each with its own Python
            self.assertIn(arch, script)


if __name__ == "__main__":
    unittest.main()
