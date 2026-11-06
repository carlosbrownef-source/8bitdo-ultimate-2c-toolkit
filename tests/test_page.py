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

    def test_back_up_comes_first_across_the_whole_width(self):
        tab = self.server.dom().find("tab-firmware")
        cols = next(n for n in tab.walk() if n.attrs.get("class") == "cols").all_text()
        self.assertNotIn("Back up", cols)
        self.assertLess(cols.index("Tweaks"), cols.index("Restore"))
        text = tab.all_text()
        self.assertLess(text.index("Back up"), text.index("Tweaks"))

    def test_help_explains_the_stick_dead_zone(self):
        text = self.server.dom().find("help").all_text()
        self.assertIn("Start + Select", text)
        self.assertIn("14 % dead zone", text)

    def test_tags_say_what_happens(self):
        text = self.server.dom().find("tab-firmware").all_text()
        self.assertNotIn("Changes the controller", text)
        self.assertIn("Installs new firmware", text)
        self.assertIn("Replaces the firmware", text)


class ControllerTestCard(PageCase):
    def body(self, query, budget=4000):
        dom = self.server.dom("&diagsim=" + query, budget)
        return dom, dom.find("test-body"), dom.find("test-body").all_text()

    def sent(self, dom):
        return dom.find("diag-sent").all_text()

    def chip(self, dom, name):
        return next(n for n in dom.find("test-seen").walk() if n.attrs.get("data-c") == name)

    def test_live_view(self):
        dom, body, text = self.body("bt&scenario=press")
        for want in ("8BitDo Ultimate 2C (X/S)", "Xbox One", "3 of 19"):
            self.assertIn(want, text)
        self.assertIn("s", self.chip(dom, "A").classes())
        self.assertNotIn("s", self.chip(dom, "B").classes())
        self.assertIn('"op":"start"', self.sent(dom))
        self.assertIn("width: 50%", dom.find("test-lt").attrs["style"])
        stick = next(n for n in body.walk() if n.attrs.get("data-k") == "LS")
        self.assertEqual(stick.attrs["transform"], "translate(5.6 -4.2)")  # GameController's up is positive, the drawing's is negative

    def test_each_drawing_has_its_own_gradient(self):
        dom = self.server.dom("&diagsim=bt")
        ids = [n.attrs["id"] for n in dom.walk() if n.tag == "lineargradient"]
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertEqual(len(ids), 2)

    def test_states(self):
        for state_, sentence in (
                ("boot", "The controller test can't run in update mode. Disconnect the controller and connect it again by Bluetooth or cable."),
                ("web", "The controller test is only available in the Mac app. Everything else in this tab works here."),
                ("none", "No controller found. Connect the controller by Bluetooth or cable to test it."),
                ("busy", "The controller test is unavailable while a task is running."),
                ("background", "The controller test is paused, because macOS only sends controller input to the app in front."),
                ("noext", "macOS sees this controller, but not as a standard gamepad, so its controls can't be tested here.")):
            self.assertIn(sentence, self.body(state_)[2], state_)

    def test_direct_report_only_over_bluetooth(self):
        dom, body, text = self.body("cable")
        self.assertIn("The direct report only works over Bluetooth.", text)
        self.assertIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "direct").attrs)
        dom, body, text = self.body("bt")
        self.assertNotIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "direct").attrs)

    def test_leaving_stops_and_coming_back_restarts(self):
        dom, _, text = self.body("bt&scenario=leave")
        self.assertRegex(self.sent(dom), r'"start".*"stop".*"start"')
        self.assertIn("0 of 19", text)

    def test_disconnect_mid_test(self):
        dom, _, text = self.body("bt&scenario=disconnect")
        self.assertIn("No controller found.", dom.find("diag-snap").all_text())
        self.assertIn("Another Pad", text)
        self.assertIn("0 of 19", text)

    def test_late_input_ignored(self):
        dom, _, text = self.body("bt&scenario=late")
        self.assertIn("1 of 19", text)
        self.assertNotIn("s", self.chip(dom, "B").classes())

    def test_vibrate_waits_for_result(self):
        dom, body, text = self.body("bt&scenario=vibrate", 6000)
        self.assertIn("disabled", dom.find("diag-snap").all_text())
        self.assertEqual(self.sent(dom).count('"op":"vibrate"'), 1)
        self.assertIn('"locality":"default"', self.sent(dom))
        self.assertIn("No answer from the app.", text)
        self.assertNotIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "default").attrs)

    def direct_button(self, body):
        return next(n for n in body.walk() if n.attrs.get("data-op") == "direct")

    def test_leaving_during_a_vibration_wait_starts_clean(self):
        dom, body, text = self.body("cable&scenario=vibrateleave", 6000)
        self.assertEqual(self.sent(dom).count('"op":"vibrate"'), 2)  # the click after coming back did something
        self.assertIn("disabled", self.direct_button(body).attrs)
        self.assertNotIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "default").attrs)

    def test_a_remount_during_a_vibration_wait_keeps_each_button_right(self):
        _, body, _ = self.body("cable&scenario=vibratestate", 6000)
        self.assertIn("disabled", self.direct_button(body).attrs)
        self.assertIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "left").attrs)
        self.assertNotIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "default").attrs)

    def test_a_result_after_its_timeout_does_not_finish_the_next_press(self):
        dom, _, _ = self.body("bt&scenario=lateresult", 6000)
        snap = dom.find("diag-snap").all_text()
        self.assertIn("disabled", snap)
        self.assertNotIn("Sent.", snap)

    def test_input_is_ignored_while_the_message_view_is_mounted(self):
        _, _, text = self.body("bt&scenario=inputafterjob")
        self.assertIn("0 of 19", text)

    def test_direct_report_line_on_bluetooth_with_the_stock_identity(self):
        _, body, text = self.body("btstock")
        self.assertIn("The direct report needs the Xbox Series X|S controller tweak.", text)
        self.assertNotIn("only works over Bluetooth", text)
        self.assertIn("disabled", self.direct_button(body).attrs)

    def test_firmware_details_name_the_tweaks(self):
        text = self.server.dom("&diagsim=boot&tweaks=1").find("firmware-details").all_text()
        self.assertIn("1.09 with 2 tweaks: Dimmer LEDs, Home ring: 5 %", text)

    def test_a_replugged_controller_is_noticed_on_the_tab(self):
        _, _, text = self.body("boot&scenario=replugged", budget=7000)
        self.assertNotIn("can't run in update mode", text)
        self.assertIn("8BitDo Ultimate 2C (X/S)", text)

    def test_tweak_controls_start_from_what_is_installed(self):
        dom, _, _ = self.body("boot&tweaks=1&scenario=installed")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,ring_5")

    def test_alerts_off_with_normal_installs_no_ring_code(self):
        dom, _, _ = self.body("boot&scenario=noalerts")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,bt_rumble,cable_360,dim_leds")

    def test_reading_the_same_firmware_keeps_the_choice_made(self):
        dom, _, _ = self.body("boot&tweaks=1&scenario=keptchoice")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,ring_1")

    def test_original_firmware_keeps_the_suggested_tweaks(self):
        dom, _, _ = self.body("boot&scenario=installed")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,bt_rumble,cable_360,dim_leds,battery_alerts,ring_normal")

    def ring_button(self, dom, index):
        return next(n for n in dom.find("ring-card").walk() if n.attrs.get("data-live") == str(index))

    def test_choosing_a_level_sends_it_at_once(self):
        dom, _, _ = self.body("bt&scenario=ringlevel")
        self.assertIn('"op":"ring","level":1,"save":false', self.sent(dom))
        self.assertIn("on", self.ring_button(dom, 1).attrs.get("class", ""))

    def test_save_sends_save(self):
        dom, _, _ = self.body("bt&scenario=ringsave")
        self.assertIn('"op":"ring","level":255,"save":true', self.sent(dom))
        self.assertIn("If the Home ring", dom.find("ring-note").all_text())

    def test_by_cable_save_says_saved(self):
        dom, _, _ = self.body("cable&tweaks=1&scenario=ringsave")
        self.assertIn("Saved", dom.find("ring-note").all_text())

    def test_reading_the_firmware_again_shows_what_it_starts_at(self):
        dom, _, _ = self.body("cable&tweaks=1&scenario=ringreread")
        self.assertIn("on", self.ring_button(dom, 2).attrs.get("class", ""))
        self.assertNotIn("on", self.ring_button(dom, 1).attrs.get("class", "").split())

    def test_over_bluetooth_nothing_is_marked_until_chosen(self):
        dom, _, _ = self.body("bt")
        self.assertFalse(any("on" in self.ring_button(dom, i).attrs.get("class", "").split() for i in range(6)))

    def test_by_cable_a_level_goes_through_the_app(self):
        dom, _, _ = self.body("cable&tweaks=1&scenario=ringlevel")
        self.assertIn("/api/ring", dom.find("diag-fetch").all_text())
        self.assertNotIn('"op":"ring"', self.sent(dom))

    def test_by_cable_the_card_shows_the_level_read(self):
        dom, _, _ = self.body("cable&tweaks=1")
        self.assertIn("on", self.ring_button(dom, 2).attrs.get("class", ""))

    def test_card_explains_when_the_tweak_is_missing(self):
        dom, _, _ = self.body("cable")
        self.assertIn("Home ring brightness", dom.find("ring-note").all_text())
        self.assertIn("disabled", self.ring_button(dom, 1).attrs)

    def test_card_explains_firmware_from_an_earlier_version(self):
        dom, _, _ = self.body("cable&tweaks=1&outdated=1")
        self.assertIn("again", dom.find("ring-note").all_text())
        self.assertIn("disabled", self.ring_button(dom, 1).attrs)

    def test_card_is_off_in_update_mode(self):
        dom, _, _ = self.body("boot")
        self.assertIn("disabled", self.ring_button(dom, 1).attrs)

    def test_no_commands_during_a_job(self):
        dom, _, _ = self.body("busy&scenario=ringlevel")
        self.assertNotIn('"op":"ring"', self.sent(dom))
        self.assertIn("disabled", self.ring_button(dom, 1).attrs)

    def test_failed_change_shows_why_and_the_previous_level(self):
        dom, _, _ = self.body("cable&tweaks=1&scenario=ringlevel&ringfail=1")
        self.assertIn("The controller said no", dom.find("ring-note").all_text())
        self.assertIn("on", self.ring_button(dom, 2).attrs.get("class", ""))

    def test_a_bluetooth_error_shows_why(self):
        dom, _, _ = self.body("bt&scenario=ringlevel&ringfail=1")
        self.assertIn("The report failed", dom.find("ring-note").all_text())
        self.assertNotIn("on", self.ring_button(dom, 1).attrs.get("class", ""))

    def test_returning_to_the_tab_doesnt_read_the_firmware_again(self):
        dom, _, _ = self.body("boot&scenario=reopen")
        self.assertEqual(dom.find("diag-fetch").all_text().count("/api/firmware"), 1)

    def test_a_connection_rereads_the_devices(self):
        _, body, _ = self.body("cable&scenario=latebt")
        self.assertNotIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "direct").attrs)

    def test_details_have_their_own_refresh(self):
        _, _, text = self.body("boot&scenario=refreshbutton")
        self.assertNotIn("can't run in update mode", text)

    def test_the_firmware_is_read_once_when_opening_the_tab(self):
        dom, _, _ = self.body("boot")
        self.assertEqual(dom.find("diag-fetch").all_text().count("/api/firmware"), 1)

    def test_report_includes_the_firmware(self):
        dom, _, _ = self.body("boot&scenario=report")
        self.assertIn("Firmware: Original 1.09", dom.find("report-text").all_text())

    def test_battery_row(self):
        for query, want in (("bt&battery=0.8,discharging", "80 %"), ("bt&battery=0.42,charging", "42 %, charging"), ("bt&battery=1,full", "Full"), ("bt&battery=0.9,unknown", "90 %"),
                            ("bt", "macOS doesn't report the battery for this controller"), ("bt&battery=-1,unknown", "macOS doesn't report the battery for this controller")):
            self.assertIn(want, self.body(query)[2], query)

    def test_a_battery_change_keeps_the_list_of_checked_controls(self):
        _, _, text = self.body("bt&scenario=batterychange")
        self.assertIn("55 %", text)
        self.assertIn("1 of 19", text)

    def test_a_change_of_device_is_noticed_without_refresh(self):
        dom = self.server.dom("&diagsim=boot&scenario=plugged", 7000)
        self.assertIn("Connected over Bluetooth", dom.find("badge-text").all_text())

    def test_the_firmware_is_not_reread_when_nothing_changes(self):
        dom = self.server.dom("&diagsim=boot", 9000)
        fetched = dom.find("diag-fetch").all_text()
        self.assertEqual(fetched.count("/api/firmware"), 1)
        self.assertGreater(fetched.count("/api/state"), 1)

    def test_nothing_is_polled_during_a_task(self):
        dom = self.server.dom("&diagsim=busy", 9000)
        self.assertLessEqual(dom.find("diag-fetch").all_text().count("/api/state"), 2)

    def test_vibration_result_lines(self):
        self.assertIn("Sent. Did you feel it?", self.body("bt&scenario=vibrateok")[2])
        self.assertIn("Sent. You'll only feel it if Rumble over Bluetooth is installed.", self.body("bt&scenario=direct")[2])
        self.assertIn("The engine failed", self.body("bt&scenario=vibrateerror")[2])

    def test_missing_locality_disables_its_button(self):
        _, body, _ = self.body("bt&scenario=defaultonly")
        self.assertIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "left").attrs)
        self.assertNotIn("disabled", next(n for n in body.walk() if n.attrs.get("data-op") == "default").attrs)

    def test_report_includes_what_macos_sees(self):
        dom, _, _ = self.body("bt&scenario=report")
        self.assertIn("macOS sees: 8BitDo Ultimate 2C (X/S) (Xbox One)", dom.find("report-text").all_text())


class HelpTest(PageCase):
    def test_help_describes_diagnostics(self):
        text = self.server.dom().find("help").all_text()
        self.assertIn("macOS may ask for your permission", text)
        self.assertIn("Diagnostics", text)
        after = text[text.index("Diagnostics"):]
        for moved in ("Controller test", "Firmware details", "Create a problem report", "Install firmware 1.09 anyway"):
            self.assertIn(moved, after)
        self.assertNotIn("Install firmware 1.09 anyway", text[:text.index("Diagnostics")])


class UnknownFirmwareTest(PageCase):
    sim = "unknown"

    def test_unknown_firmware_explains_the_two_likely_causes(self):
        text = self.server.dom().find("fw-note").all_text()
        self.assertIn("another firmware version, which you can update with 8BitDo's own updater", text)
        self.assertIn("firmware modified outside this app, which you can replace with Restore", text)

    def test_unknown_firmware_points_to_diagnostics(self):
        dom = self.server.dom()
        hint = dom.find("force-hint")
        self.assertNotIn("hidden", hint.attrs)
        self.assertIn("Open Diagnostics", hint.all_text())
        self.assertNotIn("hidden", dom.find("strip-alert").attrs)
        self.assertIn("hot", dom.find("force-zone").classes())


if __name__ == "__main__":
    unittest.main()
