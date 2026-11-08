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

    def shown_text(self):
        """Like all_text, leaving out what the hidden attribute hides."""
        return "" if "hidden" in self.attrs else " ".join([" ".join(self.text)] + [c.shown_text() for c in self.children])


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

    def test_restoring_the_original_is_on_with_firmware_1_09(self):
        dom = self.server.dom()
        self.assertNotIn("disabled", dom.find("restore-stock").attrs)
        self.assertIn("hidden", dom.find("restore-stock-why").attrs)

    def why(self, query, id_="restore-why"):
        el = self.server.dom(query).find(id_)
        return "" if "hidden" in el.attrs else el.all_text()

    def test_restore_says_why_it_is_off(self):
        self.assertEqual(self.why(""), "")
        self.assertEqual(self.why("&diagsim=cable"), "Put the controller in update mode to restore.")
        self.assertEqual(self.why("&diagsim=boot&nobackup=1"), "Back up the controller first to restore your backup.")

    def test_install_says_why_it_is_off(self):
        self.assertEqual(self.why("", "choose-one"), "")
        self.assertEqual(self.why("&diagsim=boot&scenario=notweaks", "choose-one"), "Choose at least one tweak.")

    def hero(self, query):
        dom = self.server.dom(query)
        return dom, dom.find("fw-title").all_text(), dom.find("fw-note").all_text()

    def test_the_dongle_shows_its_firmware_and_its_one_tweak(self):
        dom, title, note = self.hero("&diagsim=dongle")
        self.assertEqual((title, note), ("Dongle firmware 1.03 with tweaks", "This version of the app reads the dongle but can't change it yet."))
        self.assertEqual([" ".join(n.text) for n in dom.find("chips").children], ["Xbox 360 controller over 2.4 GHz"])
        self.assertIn("hidden", dom.find("ctrl-tweaks").attrs)
        self.assertNotIn("hidden", dom.find("dongle-tweaks").attrs)
        self.assertEqual({k: k in dom.find("dongle-360").attrs for k in ("checked", "disabled")}, {"checked": True, "disabled": True})
        self.assertEqual(dom.find("choose-one").all_text(), "This version of the app can't change the dongle yet.")
        self.assertIn("disabled", dom.find("patch-write").attrs)
        self.assertEqual(self.hero("&diagsim=dongle&stockdongle=1")[1], "Original dongle firmware 1.03")
        self.assertEqual(next(n for n in dom.find("pic").walk() if n.tag == "svg").attrs.get("aria-label"), "2.4 GHz dongle")
        text = dom.find("tab-firmware").shown_text()
        self.assertNotIn("controller", text.replace("Xbox 360 controller", ""))   # no step talks about the controller
        self.assertIn("hidden", dom.find("restore-why").attrs)

    def test_bluetooth_says_what_works_over_it(self):
        _, title, note = self.hero("&diagsim=bt")
        self.assertEqual(title, "Connected over Bluetooth")
        self.assertEqual(note, "Connect the controller by cable to see or change its firmware. Over Bluetooth, you can test it in Diagnostics and change the Home ring in Settings.")

    def test_input_monitoring_has_a_button_to_its_settings(self):
        dom = self.server.dom("&diagsim=boot&permission=1&scenario=privacy")
        self.assertNotIn("hidden", dom.find("privacy-open").attrs)
        self.assertIn('{"op":"privacy"}', dom.find("diag-sent").all_text())
        self.assertIn("hidden", self.server.dom("&diagsim=web&permission=1").find("privacy-open").attrs)   # only the Mac app can open it
        self.assertIn("hidden", self.server.dom().find("privacy-open").attrs)

    def test_hovering_check_first_or_install_shows_the_update_mode_help_until_ready(self):
        self.assertEqual(self.server.dom("&diagsim=cable&scenario=installhover").find("diag-snap").all_text(), "true")
        self.assertEqual(self.server.dom("&diagsim=boot&scenario=installhover").find("diag-snap").all_text(), "false")

    def test_update_mode_help_is_behind_the_question_mark_until_ready(self):
        dom = self.server.dom()
        self.assertEqual(dom.find("pre-boot").all_text().strip(), "In update mode")
        dom = self.server.dom("&diagsim=cable")
        self.assertEqual(dom.find("pre-boot").all_text().split(), ["Not", "in", "update", "mode", "?"])
        pop = dom.find(dom.find("boot-info").attrs["aria-controls"]).all_text()
        self.assertIn("Turn the controller fully off, then hold LB and RB", pop)
        self.assertIn("The small light below the Home ring will blink white.", pop)

    def test_the_last_resort_is_one_calm_line_unless_it_applies(self):
        dom = self.server.dom()
        zone = dom.find("force-zone")
        self.assertNotIn("hot", zone.classes())
        self.assertIn("Last-resort install for firmware that can't be identified.", zone.all_text())
        self.assertIn("Only for firmware that can't be identified", zone.all_text())
        self.assertIn("Install firmware 1.09 over an unknown version?", dom.find("force").all_text())
        self.assertNotIn("WARNING", dom.all_text())

    def test_no_hint_when_the_firmware_is_known(self):
        dom = self.server.dom()
        self.assertIn("hidden", dom.find("force-hint").attrs)
        self.assertIn("hidden", dom.find("strip-alert").attrs)

    def test_details_in_update_mode(self):
        text = " ".join(self.server.dom("&diagsim=boot").find("firmware-details").all_text().split())
        self.assertIn("Device in update mode The controller", text)
        self.assertNotIn("0x301b", text)   # the problem report keeps the number
        self.assertIn("Identified from The installed firmware", text)   # the simulation has no update record
        self.assertIn("Pending update", text)
        self.assertIn("None", text)

    def test_details_no_answer(self):
        self.assertIn("No answer", self.server.dom("&diagsim=boot&identity=none").find("firmware-details").all_text())

    def test_back_up_comes_first_across_the_whole_width(self):
        tab = self.server.dom().find("tab-firmware")
        cols = next(n for n in tab.walk() if n.attrs.get("class") == "stack").all_text()
        self.assertNotIn("Back Up", cols)
        self.assertLess(cols.index("Tweaks"), cols.index("Restore"))
        text = tab.all_text()
        self.assertLess(text.index("Back Up"), text.index("Tweaks"))

    def test_the_tweak_list_is_collapsed_at_first(self):
        dom = self.server.dom()
        self.assertEqual(dom.find("sum").all_text(), "No tweaks installed.")
        self.assertIn("hidden", dom.find("chips").attrs)
        self.assertEqual(dom.find("details").all_text(), "Show Details")
        self.assertEqual(dom.find("details").attrs.get("aria-expanded"), "false")
        self.assertIn("hidden", self.server.dom("&diagsim=bt").find("sumrow").attrs)   # nothing read, nothing to list

    def test_show_details_lists_the_installed_tweaks_first(self):
        dom = self.server.dom("&diagsim=cable&tweaks=1&scenario=details")
        self.assertEqual(dom.find("sum").all_text(), "2 tweaks installed.")
        self.assertNotIn("hidden", dom.find("chips").attrs)
        self.assertEqual((dom.find("details").all_text(), dom.find("details").attrs.get("aria-expanded")), ("Hide Details", "true"))
        chips = dom.find("chips").children
        self.assertEqual([" ".join(n.text) for n in chips[:3]], ["Xbox Series X|S controller over Bluetooth", "Home ring: 5 %", "Rumble over Bluetooth"])
        self.assertEqual(["on" in n.classes() for n in chips[:3]], [True, True, False])

    def test_the_install_row_is_pinned_at_the_end_of_the_tweaks_card(self):
        dom = self.server.dom()
        card = dom.find("tweaks-card")
        row = card.children[-1]
        self.assertEqual((row.attrs.get("id"), row.classes()), ("tweaks-act", ["act"]))
        for id_ in ("pre-backup", "pre-boot", "patch-dry", "patch-write", "choose-one"):
            self.assertIsNotNone(row.find(id_), id_)
        self.assertIn("Installing modified firmware probably voids the controller's warranty.", row.all_text())
        css = (Path(__file__).parent.parent / "u2c_customfw/web/static/style.css").read_text()
        for rule in ("main{flex:1;overflow:auto;padding:14px 22px}", ".act{position:sticky;bottom:-14px", ".set-actions{position:sticky;bottom:-14px"):   # main's bottom padding
            self.assertIn(rule, css)

    def test_the_hero_says_where_the_version_came_from(self):
        self.assertEqual(self.hero("")[2], "Identified from the installed firmware")

    def test_buttons_are_title_case(self):
        dom = self.server.dom()
        labels = {id_: dom.find(id_).all_text() for id_ in ("backup", "patch-dry", "patch-write", "restore-backup-dry", "settings-save", "settings-reset", "report-open", "force-open", "force-yes")}
        self.assertEqual(labels, {"backup": "Back Up", "patch-dry": "Check First", "patch-write": "Install Tweaks…", "restore-backup-dry": "Check First",
                                  "settings-save": "Save to Controller", "settings-reset": "Reset to Defaults…", "report-open": "Create Problem Report",
                                  "force-open": "Install Firmware 1.09 Anyway…", "force-yes": "Install Anyway"})

    def test_the_back_up_step_asks_for_the_cable_only_without_a_controller(self):
        self.assertIn("hidden", self.server.dom().find("backup-connect").attrs)
        self.assertNotIn("hidden", self.server.dom("&diagsim=bt").find("backup-connect").attrs)

    def test_help_explains_the_stick_dead_zone(self):
        text = self.server.dom().find("help").all_text()
        self.assertIn("− (Select) and + (Start)", text)
        self.assertIn("14 % dead zone", text)

    def test_tags_say_what_happens(self):
        text = self.server.dom().find("tab-firmware").all_text()
        self.assertNotIn("Changes the controller", text)
        self.assertIn("Installs new firmware", text)
        self.assertIn("Replaces the firmware", text)


class SettingsTabTest(PageCase):
    READY = "&diagsim=cable&tweaks=1&settings=1&open=settings"

    def control(self, dom, field):
        return next(n for n in dom.find("settings-cards").walk() if n.attrs.get("data-field") == field)

    def test_settings_tab_opens(self):
        dom = self.server.dom(self.READY)
        self.assertNotIn("hidden", dom.find("tab-settings").attrs)
        self.assertIn("hidden", dom.find("tab-firmware").attrs)
        self.assertIn("on", dom.find("strip-settings").classes())
        self.assertNotIn("hidden", dom.find("settings-cards").attrs)
        self.assertIn("Vibration", dom.find("settings-cards").all_text())

    def test_tabs_are_in_order(self):
        strip = self.server.dom(self.READY).find("strip-firmware")
        self.assertIsNotNone(strip)
        ids = [n.attrs["id"] for n in self.server.dom(self.READY).walk() if n.attrs.get("id", "").startswith("strip-") and n.attrs["id"] != "strip-alert"]
        self.assertEqual(ids, ["strip-firmware", "strip-settings", "strip-diagnostics"])

    def test_ring_card_moved_to_settings(self):
        dom = self.server.dom(self.READY)
        self.assertIsNotNone(dom.find("tab-settings").find("ring-card"))
        self.assertIsNone(dom.find("tab-diagnostics").find("ring-card"))

    def test_shows_what_the_controller_keeps(self):
        dom = self.server.dom(self.READY)
        self.assertIn("on", next(n for n in self.control(dom, "vibration").walk() if n.attrs.get("data-value") == "100").classes())

    def explains(self, query, text):
        dom = self.server.dom(query)
        self.assertIn("hidden", dom.find("settings-cards").attrs, query)
        self.assertIn(text, dom.find("settings-note").all_text(), query)

    def test_tab_explains_bluetooth(self):
        self.explains("&diagsim=bt&open=settings", "by cable")

    def test_tab_explains_missing_tweak(self):
        self.explains("&diagsim=cable&tweaks=1&open=settings", "Controller settings isn't installed. Install it in the Firmware tab")

    def test_a_missing_tweak_offers_the_way_to_the_firmware_tab(self):
        dom = self.server.dom("&diagsim=cable&tweaks=1&open=settings")
        self.assertNotIn("hidden", dom.find("settings-goto").attrs)
        self.assertEqual(dom.find("settings-goto").all_text(), "Open Firmware Tab")
        self.assertIn("hidden", self.server.dom("&diagsim=bt&open=settings").find("settings-goto").attrs)
        dom = self.server.dom("&diagsim=cable&tweaks=1&open=settings&scenario=gotofirmware")
        self.assertNotIn("hidden", dom.find("tab-firmware").attrs)

    def test_tab_explains_update_mode(self):
        self.explains("&diagsim=boot&open=settings", "update mode")

    def test_tab_explains_firmware_from_an_earlier_version(self):
        self.explains("&diagsim=cable&tweaks=1&outdated=1&open=settings", "Install it in the Firmware tab")

    def test_tab_says_nothing_is_sent_during_a_job(self):
        dom = self.server.dom("&diagsim=busy&open=settings", 7000)
        self.assertIn("task", dom.find("settings-note").all_text())

    def test_a_change_goes_to_the_app_and_unsaved_note_appears(self):
        dom = self.server.dom(self.READY + "&scenario=setvibration")
        self.assertIn('{"set":{"vibration":50}}', dom.find("diag-posted").all_text())
        self.assertIn("on", next(n for n in self.control(dom, "vibration").walk() if n.attrs.get("data-value") == "50").classes())
        self.assertNotIn("hidden", dom.find("settings-unsaved").attrs)

    def test_unsaved_note_appears_and_clears(self):
        dom = self.server.dom(self.READY + "&scenario=setandsave")
        self.assertIn('"save":true', dom.find("diag-posted").all_text())
        self.assertIn('"vibration":50', dom.find("diag-posted").all_text())
        self.assertIn("hidden", dom.find("settings-unsaved").attrs)
        self.assertIn("Saved", dom.find("settings-message").all_text())

    def test_failed_change_returns_control_to_true_value(self):
        dom = self.server.dom(self.READY + "&settingsfail=1&scenario=setvibration")
        self.assertIn("on", next(n for n in self.control(dom, "vibration").walk() if n.attrs.get("data-value") == "100").classes())
        self.assertIn("said no", dom.find("settings-message").all_text())
        self.assertIn("hidden", dom.find("settings-unsaved").attrs)

    def test_a_failed_save_stays_unsaved(self):
        dom = self.server.dom(self.READY + "&scenario=setandfailsave")
        self.assertNotIn("hidden", dom.find("settings-unsaved").attrs)
        self.assertIn("said no", dom.find("settings-message").all_text())

    def test_reset_asks_first(self):
        dom = self.server.dom(self.READY + "&scenario=resetopen")
        self.assertNotIn('"reset"', dom.find("diag-posted").all_text())
        self.assertIn("open", dom.find("confirm").attrs)
        dom = self.server.dom(self.READY + "&scenario=resetyes")
        self.assertIn('{"reset":true}', dom.find("diag-posted").all_text())

    def test_installing_includes_settings_by_default_with_the_ring_code(self):
        dom = self.server.dom("&diagsim=boot&scenario=installed")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,bt_rumble,cable_360,dim_leds,battery_alerts,settings,fixes,cpu_rest,ring_normal")

    def test_sticks_and_triggers_have_their_controls(self):
        dom = self.server.dom(self.READY)
        for field in ("dz_l", "dz_r", "outer_l", "outer_r", "curve_l", "curve_r", "lt_start", "lt_end", "rt_start", "rt_end"):
            self.assertIsNotNone(self.control(dom, field), field)
        dz = self.control(dom, "dz_l")
        self.assertEqual((dz.attrs["min"], dz.attrs["max"], dz.attrs["value"]), ("0", "30", "14"))
        self.assertEqual(sum(n.attrs.get("data-field") == "invert" for n in dom.find("settings-cards").walk()), 4)

    def test_a_slider_sends_when_it_is_let_go(self):
        dom = self.server.dom(self.READY + "&scenario=dragdz")
        self.assertEqual(dom.find("diag-posted").all_text().strip(), '{"set":{"dz_l":9}}')
        self.assertEqual(self.control(dom, "dz_l").attrs["value"], "9")
        self.assertIn("9 %", dom.find("settings-cards").all_text())

    def test_an_axis_changes_one_bit_of_the_invert_field(self):
        dom = self.server.dom(self.READY + "&scenario=invert")
        self.assertIn('{"set":{"invert":5}}', dom.find("diag-posted").all_text())

    def test_live_view_on_settings(self):
        dom = self.server.dom(self.READY + "&scenario=liveinput")
        self.assertIn("start", dom.find("diag-sent").all_text())
        self.assertIn("translate(", dom.find("live-left").attrs.get("style", ""))
        self.assertIn("width: 50%", dom.find("live-lt").attrs.get("style", ""))
        self.assertIn("hidden", dom.find("live-note").attrs)

    def test_leaving_settings_stops_it(self):
        dom = self.server.dom(self.READY + "&scenario=leavesettings")
        sent = dom.find("diag-sent").all_text()
        self.assertGreater(sent.rindex('"stop"'), sent.rindex('"start"'))

    def test_going_to_diagnostics_keeps_the_controller_test_running(self):
        dom = self.server.dom(self.READY + "&scenario=settingstodiag")
        sent = dom.find("diag-sent").all_text()
        self.assertGreater(sent.rindex('"start"'), sent.rindex('"stop"'))

    def test_settings_work_without_the_bridge(self):
        dom = self.server.dom("&diagsim=web&tweaks=1&settings=1&open=settings&scenario=setvibration")
        self.assertIn("Mac app", dom.find("live-note").all_text())
        self.assertIn('{"set":{"vibration":50}}', dom.find("diag-posted").all_text())

    def test_a_ring_answer_arrives_while_on_this_tab(self):
        dom = self.server.dom("&diagsim=bt&open=settings&scenario=ringlevel")
        self.assertNotIn("No answer", dom.find("ring-note").all_text())
        self.assertIn("Sent", dom.find("ring-note").all_text())

    def test_the_save_row_is_pinned_at_the_bottom_and_says_how_saving_works(self):
        dom = self.server.dom(self.READY)
        tab = dom.find("tab-settings")
        ids = [n.attrs["id"] for n in tab.walk() if n.attrs.get("id") in ("settings-actions", "ring-card", "live-card", "settings-cards")]
        self.assertEqual(ids, ["ring-card", "live-card", "settings-cards", "settings-actions"])
        row = tab.children[-1]
        self.assertEqual(row.attrs.get("id"), "settings-actions")
        self.assertNotIn("hidden", row.attrs)
        for id_ in ("settings-save", "settings-reset", "settings-unsaved", "settings-message"):
            self.assertIsNotNone(row.find(id_), id_)
        self.assertIn("Changes apply at once. Save them to keep them after the controller turns off.", dom.find("settings-actions").all_text())
        self.assertEqual(dom.find("ring-save").all_text(), "Save Ring Level")
        self.assertNotIn("Changes at once", tab.all_text())
        self.assertIn("Live View", dom.find("live-card").all_text())
        slots = [n.attrs["data-slot"] for n in dom.find("settings-cards").walk() if n.attrs.get("data-slot") and n.attrs.get("data-bit") == "13"]
        self.assertEqual(slots, ["l4", "r4"])

    def test_mapping_warning_text(self):
        text = " ".join(self.server.dom(self.READY).find("settings-cards").all_text().split())
        self.assertIn("Pressing L4 and R4 together changes the Home ring's brightness, and games also receive the buttons you mapped to them.", text)

    def mapping_buttons(self, dom, slot):
        return [n for n in dom.find("settings-cards").walk() if n.attrs.get("data-slot") == slot]

    def test_mapping_choices_exclude_paddles(self):
        dom = self.server.dom(self.READY)
        for slot in ("r4", "l4"):
            names = [" ".join(n.text).strip() for n in self.mapping_buttons(dom, slot)]
            self.assertEqual(sorted(names), sorted(["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "Left stick press", "Right stick press", "− (Select)", "+ (Start)", "D-pad up", "D-pad down", "D-pad left", "D-pad right"]))

    def test_mapping_is_sent_as_bits(self):
        dom = self.server.dom(self.READY + "&scenario=mapa")
        posted = dom.find("diag-posted").all_text()
        self.assertIn('{"mapping":{"slot":"r4","mask":8192}}', posted)  # A is bit 13
        self.assertIn('{"mapping":{"slot":"r4","mask":12288}}', posted)  # then B too, bit 12
        self.assertNotIn("hidden", dom.find("settings-unsaved").attrs)

    def test_mapping_shows_what_is_kept(self):
        dom = self.server.dom(self.READY + "&mapped=1")
        on = [" ".join(n.text).strip() for n in self.mapping_buttons(dom, "l4") if "on" in n.classes()]
        self.assertEqual(on, ["LT"])

    def test_dead_zone_switch_has_a_control_and_shows_its_state(self):
        dom = self.server.dom(self.READY + "&scenario=dzoff")
        self.assertIn('{"dead_zone_off":true}', dom.find("diag-posted").all_text())
        self.assertIn("− (Select) and + (Start)", dom.find("settings-cards").all_text())

    def test_calibration_steps_send_nothing(self):
        dom = self.server.dom(self.READY)
        text = dom.find("settings-cards").all_text()
        self.assertIn("− (Select), + (Start), LB and RB", text)
        self.assertIn("7 seconds", text)
        self.assertEqual(dom.find("diag-posted").all_text().strip(), "")

    def test_remap_shows_every_button_once(self):
        dom = self.server.dom(self.READY)
        rows = [n for n in dom.find("settings-cards").walk() if n.attrs.get("data-field", "").startswith("remap_")]
        self.assertEqual(sorted(n.attrs["data-field"] for n in rows), sorted(f"remap_{i}" for i in range(14)))
        self.assertEqual({len([o for o in n.walk() if o.tag == "option"]) for n in rows}, {15})

    def test_remap_shows_the_kept_choice_and_sends_a_change(self):
        dom = self.server.dom(self.READY + "&scenario=remap")
        self.assertIn('{"set":{"remap_13":12}}', dom.find("diag-posted").all_text())
        row = self.control(dom, "remap_13")
        self.assertEqual(row.attrs.get("data-now"), "12")

    def test_remap_can_be_reset(self):
        dom = self.server.dom(self.READY + "&scenario=remapreset")
        self.assertEqual(self.control(dom, "remap_13").attrs.get("data-now"), "13")
        self.assertIn("hidden", dom.find("settings-unsaved").attrs)

    def test_controls_are_off_while_a_change_is_on_its_way(self):
        dom = self.server.dom(self.READY + "&slow=1&scenario=setvibration", 1200)
        self.assertIn("disabled", next(n for n in self.control(dom, "vibration").walk() if n.attrs.get("data-value") == "50").attrs)


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
        self.assertEqual(len(ids), 3)   # the hero, the controller test and the update-mode pop-up

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
        text = " ".join(self.server.dom("&diagsim=boot&tweaks=1").find("firmware-details").all_text().split())
        self.assertIn("Firmware 1.09 with 2 tweaks Dimmer LEDs Home ring: 5 %", text)   # one per line

    def test_a_replugged_controller_is_noticed_on_the_tab(self):
        _, _, text = self.body("boot&scenario=replugged", budget=7000)
        self.assertNotIn("can't run in update mode", text)
        self.assertIn("8BitDo Ultimate 2C (X/S)", text)

    def test_tweak_controls_start_from_what_is_installed(self):
        dom, _, _ = self.body("boot&tweaks=1&scenario=installed")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,ring_5")

    def test_alerts_off_with_normal_installs_no_ring_code(self):  # with the other tweaks that need it off too
        dom, _, _ = self.body("boot&scenario=noalerts")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,bt_rumble,cable_360,dim_leds")

    def test_reading_the_same_firmware_keeps_the_choice_made(self):
        dom, _, _ = self.body("boot&tweaks=1&scenario=keptchoice")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,cable_360,ring_5")

    def test_original_firmware_keeps_the_suggested_tweaks(self):
        dom, _, _ = self.body("boot&scenario=installed")
        self.assertEqual(dom.find("diag-snap").all_text(), "bt_xbox,bt_rumble,cable_360,dim_leds,battery_alerts,settings,fixes,cpu_rest,ring_normal")

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
        self.assertIn("Install the tweaks", dom.find("ring-note").all_text())
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

    def test_one_read_again_button(self):
        dom = self.server.dom("&diagsim=boot")
        self.assertEqual(dom.find("refresh").all_text(), "Read Again")
        self.assertIsNone(dom.find("details-refresh"))

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
        dom = self.server.dom("&diagsim=boot&scenario=replugged", 7000)
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


class ConfirmTest(PageCase):
    def test_restoring_the_backup_names_it_and_isnt_styled_as_danger(self):
        dom = self.server.dom("&diagsim=boot&scenario=restoreask")
        self.assertIn("open", dom.find("confirm").attrs)
        self.assertIn("“controller-sim.bin”, made on", dom.find("confirm-text").all_text())
        self.assertIn("the original firmware 1.09", dom.find("confirm-text").all_text())
        self.assertNotIn("danger", dom.find("confirm-yes").classes())
        self.assertIn("hidden", dom.find("confirm-icon").attrs)
        self.assertIn("hidden", dom.find("confirm-warranty").attrs)

    def test_the_restore_sends_the_backup_it_named(self):
        self.assertIn('"backup":"controller-sim.bin"', self.server.dom("&diagsim=boot&scenario=restorecheck").find("diag-posted").all_text())

    def test_installing_warns_about_the_warranty(self):
        dom = self.server.dom("&diagsim=boot&scenario=installask")
        self.assertIn("danger", dom.find("confirm-yes").classes())
        self.assertNotIn("hidden", dom.find("confirm-icon").attrs)
        self.assertNotIn("hidden", dom.find("confirm-warranty").attrs)
        self.assertIn("Installing modified firmware probably voids the controller's warranty.", dom.find("confirm-text").all_text())

    def test_each_tweak_says_what_it_does_and_the_chips_keep_its_name(self):
        dom = self.server.dom("&diagsim=boot&scenario=installask")
        rows = [n for n in dom.find("ctrl-tweaks").walk() if "tw" in n.classes()]
        self.assertEqual(len(rows), 10)
        pops = {n.attrs["id"]: n for n in dom.walk() if "pop" in n.classes()}
        for row in rows:   # each explanation is in a pop-up behind its (i) button, outside the row
            info = next(n for n in row.walk() if "info" in n.classes())
            self.assertEqual(info.tag, "button")
            line = pops[info.attrs["aria-controls"]].all_text()
            self.assertTrue(line.endswith("."), line)
            self.assertFalse(any(n.tag == "small" for n in row.walk()), row.all_text())
        notes = {next(n for n in row.walk() if n.tag == "input").attrs["value"]: next((n.all_text() for n in row.walk() if "note" in n.classes()), None) for row in rows}
        self.assertEqual(notes["bt_rumble"], "Needs Xbox Series X|S controller over Bluetooth.")
        self.assertEqual(sum(1 for v in notes.values() if v), 3)   # Rumble, Finer stick movement, Faster button reading
        self.assertFalse(any("data-ring" in n.attrs for n in dom.find("tab-firmware").walk()))   # the ring is set in Settings only
        chips = [" ".join(n.text) for n in dom.find("confirm-chips").children]
        self.assertIn("Rumble over Bluetooth", chips)

    def test_the_info_button_opens_its_pop_up_without_toggling_the_tweak(self):
        dom = self.server.dom("&diagsim=boot&scenario=infopop")
        self.assertEqual(dom.find("diag-snap").all_text(), "false true")

    def test_reset_is_not_styled_as_danger(self):
        dom = self.server.dom(SettingsTabTest.READY + "&scenario=resetopen")
        self.assertNotIn("danger", dom.find("confirm-yes").classes())
        self.assertIn("hidden", dom.find("confirm-warranty").attrs)


class DockTest(PageCase):
    def end(self, scenario, job):
        dom = self.server.dom(f"&diagsim=boot&job={job}&scenario={scenario}")
        return dom, dom.find("dock-status").all_text(), dom.find("dock-message")

    def test_a_backup_says_what_it_saved(self):
        dom, status, message = self.end("backupjob", "backup")
        self.assertEqual(status, "Backup saved")
        self.assertNotIn("hidden", message.attrs)
        self.assertIn("Backup saved as “controller-", message.all_text())
        self.assertIn("hidden", dom.find("log").attrs)   # the log starts collapsed
        self.assertIn("Show Log", dom.find("log-toggle").all_text())

    def test_a_check_says_it_passed_and_what_installing_changes(self):
        _, status, message = self.end("checkjob", "check")
        self.assertEqual(status, "Check passed")
        self.assertIn("The check passed and nothing was written. Installing changes", message.all_text())

    def test_a_write_says_not_to_disconnect_and_then_what_to_do(self):
        dom, status, message = self.end("installjob", "install")
        self.assertIn("Do not disconnect the controller or quit the app until this finishes.", dom.find("diag-snap").all_text())
        self.assertEqual(status, "Tweaks installed")
        self.assertTrue(message.all_text().startswith("Installed. Unplug the controller and connect it again."))
        self.assertIn("hidden", dom.find("idle").attrs)

    def test_a_refusal_is_not_completed_with_its_reason_in_plain_text(self):
        dom, status, message = self.end("checkjob", "refused")
        self.assertEqual(status, "Not completed")
        self.assertIn("err", dom.find("dock").classes())
        self.assertIn("nothing was written", message.all_text())

    def test_nothing_to_write_isnt_called_installed(self):
        self.assertEqual(self.end("checkjob", "unchanged")[1], "No changes needed")

    def test_the_dock_is_announced(self):
        dom, _, _ = self.end("checkjob", "check")
        self.assertEqual(dom.find("dock-status").attrs.get("aria-live"), "polite")
        self.assertEqual((dom.find("prog").attrs.get("role"), dom.find("prog").attrs.get("aria-valuenow")), ("progressbar", "100"))


class AccessibilityTest(PageCase):
    def pressed(self, dom, attr):
        return {n.attrs[attr]: n.attrs.get("aria-pressed") for n in dom.walk() if attr in n.attrs and n.tag == "button"}

    def test_segmented_controls_and_chips_say_which_is_chosen(self):
        dom = self.server.dom()
        self.assertEqual(self.pressed(dom, "data-base"), {"backup": "true", "download": "false"})
        dom = self.server.dom(SettingsTabTest.READY + "&mapped=1")
        vibration = next(n for n in dom.find("settings-cards").walk() if n.attrs.get("data-field") == "vibration")
        self.assertEqual({b.attrs["data-value"]: b.attrs.get("aria-pressed") for b in vibration.walk() if b.tag == "button"}["100"], "true")
        chips = {(b.attrs["data-slot"], b.attrs["data-bit"]): b.attrs.get("aria-pressed") for b in dom.walk() if "data-slot" in b.attrs}
        self.assertEqual((chips[("l4", "14")], chips[("r4", "14")], chips[("l4", "13")]), ("true", "false", "false"))

    def test_tabs_are_tabs(self):
        dom = self.server.dom("&diagsim=boot&open=settings")
        self.assertEqual(next(n for n in dom.walk() if n.attrs.get("role") == "tablist").tag, "div")
        self.assertEqual([(dom.find(f"strip-{t}").attrs.get("role"), dom.find(f"strip-{t}").attrs.get("aria-selected")) for t in ("firmware", "settings", "diagnostics")],
                         [("tab", "false"), ("tab", "true"), ("tab", "false")])
        self.assertEqual(dom.find("tab-settings").attrs.get("role"), "tabpanel")

    def test_the_vibration_buttons_name_the_motors(self):
        text = self.server.dom("&diagsim=bt").find("test-body").all_text()
        self.assertIn("Left Motor", text)
        self.assertIn("Right Motor", text)


class SmallerTest(PageCase):
    def test_the_firmware_source_is_capitalised_like_the_other_choices(self):
        dom = self.server.dom()
        self.assertEqual([" ".join(n.text) for n in dom.walk() if "data-base" in n.attrs], ["Your Backup", "8BitDo's Server"])

    def test_back_up_steps_back_once_there_is_a_backup(self):
        self.assertIn("sec", self.server.dom().find("backup").classes())
        self.assertNotIn("sec", self.server.dom("&diagsim=boot&nobackup=1").find("backup").classes())

    def test_the_disclaimer_can_be_declined_in_the_mac_app(self):
        dom = self.server.dom("&diagsim=boot&scenario=quit")
        self.assertNotIn("hidden", dom.find("disclaimer-quit").attrs)
        self.assertEqual(dom.find("disclaimer-quit").all_text(), "Quit")
        self.assertIn('{"op":"quit"}', dom.find("diag-sent").all_text())
        self.assertIn("hidden", self.server.dom("&diagsim=web").find("disclaimer-quit").attrs)


class HelpTest(PageCase):
    def test_help_states_the_same_facts_and_risks_as_the_readme(self):
        text = self.server.dom().find("help").all_text()
        for fact in ("about 1.25 ms sooner", "a worn button could occasionally register twice.",
                     "In rare cases it could make the controller stop responding. This hasn't been observed.",
                     "Installing keeps the ring's level as it is, and you change it in the Settings tab."):
            self.assertIn(fact, text)
        for promise in ("saves battery", "battery life"):   # not claimed until it's measured
            self.assertNotIn(promise, text.lower())
            self.assertNotIn(promise, self.server.dom().find("tab-firmware").all_text().lower())
            self.assertNotIn(promise, (Path(__file__).parent.parent / "README.md").read_text().lower())
        self.assertNotIn("about 1 ms", text)
        self.assertIn("Backups are kept on this Mac, in ~/Library/Application Support/u2c-customfw.", text)
        self.assertEqual(text.count("It needs the Home ring's code."), 3)   # Battery alerts, Controller settings and Fixes
        order = [text.rindex(t + ".") for t in ("Xbox Series X|S controller over Bluetooth", "Rumble over Bluetooth", "Xbox 360 controller over cable", "Dimmer LEDs",
                                              "Battery alerts", "Controller settings", "Fixes", "Processor rest", "Finer stick movement", "Faster button reading")]
        self.assertEqual(order, sorted(order))

    def test_the_hero_lists_the_tweaks_in_the_toggles_order(self):
        dom = self.server.dom()
        chips = [" ".join(n.text) for n in dom.find("chips").children]
        self.assertEqual(chips[:3], ["Xbox Series X|S controller over Bluetooth", "Rumble over Bluetooth", "Xbox 360 controller over cable"])
        self.assertLess(chips.index("Processor rest between radio events"), chips.index("Finer stick movement"))
        self.assertTrue(chips[-1].startswith("Home ring"))
    def test_help_opens_at_the_top_with_its_contents(self):
        dom = self.server.dom("&diagsim=boot&scenario=helpopen")
        self.assertEqual(dom.find("diag-snap").all_text(), "help-top 0 diagnostics")   # update mode opens on Diagnostics
        side = [n for n in dom.find("help").walk() if "data-help" in n.attrs]
        self.assertEqual([" ".join(n.text) for n in side], ["Getting Started", "Tweaks", "Settings", "Diagnostics"])
        parts = {n.attrs["data-hsec"]: n for n in dom.find("help").walk() if "data-hsec" in n.attrs}
        self.assertEqual(sorted(parts), sorted(n.attrs["data-help"] for n in side))
        self.assertEqual([n.attrs["data-hsec"] for n in parts.values() if "hidden" not in n.attrs], ["diagnostics"])

    def test_help_opens_on_the_section_of_the_tab_in_view(self):
        self.assertEqual(self.server.dom("&diagsim=cable&scenario=helpsettings").find("diag-snap").all_text(), "settings")

    def test_help_describes_diagnostics(self):
        text = self.server.dom().find("help").all_text()
        self.assertIn("macOS may ask for your permission", text)
        self.assertIn("Diagnostics", text)
        after = text[text.index("Diagnostics"):]
        for moved in ("Controller Test", "Firmware Details", "Create Problem Report", "Install Firmware 1.09 Anyway"):
            self.assertIn(moved, after)
        self.assertNotIn("Install Firmware 1.09 Anyway", text[:text.index("Diagnostics")])


class UnknownFirmwareTest(PageCase):
    sim = "unknown"

    def test_unknown_firmware_explains_the_two_likely_causes(self):
        text = self.server.dom().find("fw-note").all_text()
        self.assertIn("another firmware version, which you can update with 8BitDo's own updater", text)
        self.assertIn("firmware modified outside this app, which restoring your backup replaces", text)

    def test_install_says_why_it_is_off(self):
        el = self.server.dom().find("choose-one")
        self.assertNotIn("hidden", el.attrs)
        self.assertEqual(el.all_text(), "This firmware can't be identified. Restore your backup first.")

    def test_restoring_the_original_is_off_with_its_reason(self):
        dom = self.server.dom()
        for id_ in ("restore-stock", "restore-stock-dry"):
            self.assertIn("disabled", dom.find(id_).attrs, id_)
        self.assertIn("Not available, because the firmware version can't be identified.", dom.find("restore-stock-why").all_text())
        self.assertNotIn("hidden", dom.find("restore-stock-why").attrs)
        self.assertIn("If restoring your backup doesn't repair it", dom.find("force-hint").all_text())

    def test_unknown_firmware_points_to_diagnostics(self):
        dom = self.server.dom()
        hint = dom.find("force-hint")
        self.assertNotIn("hidden", hint.attrs)
        self.assertIn("Open Diagnostics", hint.all_text())
        self.assertNotIn("hidden", dom.find("strip-alert").attrs)
        self.assertIn("hot", dom.find("force-zone").classes())


if __name__ == "__main__":
    unittest.main()
