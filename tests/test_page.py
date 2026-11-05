# SPDX-License-Identifier: GPL-3.0-or-later
"""The page in headless Chrome, against the simulated controller. Skipped where Chrome isn't installed."""
import os
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from u2c_customfw import state

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.children, self.text = tag, dict(attrs), [], []

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def find(self, id_):
        return next((n for n in self.walk() if n.attrs.get("id") == id_), None)

    def all_text(self):
        return " ".join(" ".join(n.text) for n in self.walk())

    def classes(self):
        return self.attrs.get("class", "").split()


class Tree(HTMLParser):
    def __init__(self, dom):
        super().__init__()
        self.root = Node("root", [])
        self.stack = [self.root]
        self.feed(dom)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if data.strip():
            self.stack[-1].text.append(data.strip())


class Server:
    def __init__(self, sim):
        self.store = tempfile.mkdtemp()
        state.accept(Path(self.store))
        env = dict(os.environ, U2C_SIM=sim, PYTHONPATH=str(Path(__file__).parent.parent))
        self.proc = subprocess.Popen([sys.executable, "-m", "u2c_customfw.web", self.store], stdout=subprocess.PIPE, text=True, env=env)
        line = self.proc.stdout.readline()
        self.url = line.split()[1]

    def dom(self, query="", budget=4000):
        out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={self.store}/chrome", f"--virtual-time-budget={budget}",
                              "--dump-dom", self.url + query], capture_output=True, text=True, timeout=120)
        return Tree(out.stdout).root

    def stop(self):
        self.proc.terminate()
        self.proc.wait()
        self.proc.stdout.close()


@unittest.skipUnless(os.path.exists(CHROME), "needs Google Chrome")
class PageCase(unittest.TestCase):
    sim = "1"

    @classmethod
    def setUpClass(cls):
        cls.server = Server(cls.sim)
        cls.addClassCleanup(cls.server.stop)


class TabsTest(PageCase):
    def test_opens_on_firmware(self):
        dom = self.server.dom()
        self.assertNotIn("hidden", dom.find("tab-firmware").attrs)
        self.assertIn("hidden", dom.find("tab-diagnostics").attrs)

    def test_diagnostics_holds_the_moved_cards(self):
        dom = self.server.dom()
        diagnostics, firmware = dom.find("tab-diagnostics"), dom.find("tab-firmware")
        for id_ in ("report-open", "force-zone", "firmware-details", "test-card"):
            self.assertIsNotNone(diagnostics.find(id_), id_)
            self.assertIsNone(firmware.find(id_), id_)

    def test_install_anyway_says_what_happens(self):
        self.assertIn("Erases the firmware on the controller and replaces it with 8BitDo's original firmware 1.09, without any tweaks.",
                      self.server.dom().find("force-zone").all_text())

    def test_no_hint_when_the_firmware_is_known(self):
        dom = self.server.dom()
        self.assertIn("hidden", dom.find("force-hint").attrs)
        self.assertIn("hidden", dom.find("strip-alert").attrs)

    def test_details_in_update_mode(self):
        text = self.server.dom("&diagsim=boot").find("firmware-details").all_text()
        self.assertIn("0x301b · controller", text)
        self.assertIn("Pending update", text)
        self.assertIn("None", text)

    def test_details_no_answer(self):
        self.assertIn("No answer", self.server.dom("&diagsim=boot&identity=none").find("firmware-details").all_text())

    def test_tags_say_what_happens(self):
        text = self.server.dom().find("tab-firmware").all_text()
        self.assertNotIn("Changes the controller", text)
        self.assertIn("Installs new firmware", text)
        self.assertIn("Replaces the firmware", text)


class UnknownFirmwareTest(PageCase):
    sim = "unknown"

    def test_unknown_firmware_points_to_diagnostics(self):
        dom = self.server.dom()
        hint = dom.find("force-hint")
        self.assertNotIn("hidden", hint.attrs)
        self.assertIn("Open Diagnostics", hint.all_text())
        self.assertNotIn("hidden", dom.find("strip-alert").attrs)
        self.assertIn("hot", dom.find("force-zone").classes())


if __name__ == "__main__":
    unittest.main()
