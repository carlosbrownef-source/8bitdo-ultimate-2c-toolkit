# SPDX-License-Identifier: GPL-3.0-or-later
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from unittest import mock

from u2c_customfw import cli, state
from u2c_customfw.firmware import image, recipes
from u2c_customfw.ops import devices, probe
from u2c_customfw import transport
from u2c_customfw.protocol import app
from u2c_customfw.sim import SimApp
from tests.test_ops import K, STOCK_A, controller_flash
from u2c_customfw.web import jobs, server


class WebTest(unittest.TestCase):
    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        self.httpd, self.token = server.make_server(self.store, 0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.saved = dict(jobs.ACTIONS)
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close(), jobs.ACTIONS.update(self.saved)))

    def call(self, method, path, body=None, token="auto"):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body or {}).encode() if method == "POST" else None)
        if token:
            req.add_header("X-Token", self.token if token == "auto" else token)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            e.close()
            return e.code, body

    def events(self):
        status, text = self.call("GET", "/api/events")
        self.assertEqual(status, 200)
        return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]

    def test_report_endpoint_with_a_bad_body(self):
        with mock.patch.object(cli, "find", lambda: []):
            for body in ({"macos": "x"}, {"boot_identity": "x"}, {"macos": {"name": 5}}):
                self.assertEqual(self.call("POST", "/api/report", body)[0], 200)

    def test_report_endpoint_uses_the_extras(self):
        with mock.patch.object(cli, "find", lambda: []):
            text = json.loads(self.call("POST", "/api/report", {"macos": {"name": "Pad"}, "pending": True})[1])["text"]
        self.assertIn("Pad", text)
        self.assertIn("Pending update: yes", text)

    def ring_call(self, body, flash=None, mode="cable_360"):
        built = recipes.build(STOCK_A, ["ring_5"], **K)
        info = transport.DeviceInfo(0x045E, 0x028E, 0xFF7A, "USB", "x", None)
        self.dev = SimApp(controller_flash(built) if flash is None else flash)
        with mock.patch.object(cli, "find", lambda: [devices.Found(info, mode)]), mock.patch.object(cli, "open_channel", lambda i, rid: self.dev):
            return self.call("POST", "/api/ring", body)

    def test_api_ring_sends_the_level(self):
        sent = []
        with mock.patch.object(app, "set_ring", lambda ch, level: sent.append(level)):
            self.assertEqual(self.ring_call({"level": 2})[0], 200)
        self.assertEqual(sent, [2])

    def test_api_ring_saves(self):
        sent = []
        with mock.patch.object(app, "save_ring", lambda ch: sent.append("save")):
            self.assertEqual(self.ring_call({"save": True})[0], 200)
        self.assertEqual(sent, ["save"])

    def test_api_ring_refuses_an_unknown_level(self):
        for level in (6, -1, "2", 1.5):
            self.assertEqual(self.ring_call({"level": level})[0], 400, level)
        self.assertEqual(self.ring_call({})[0], 400)

    def test_api_ring_refuses_without_the_tweak(self):
        status, text = self.ring_call({"level": 2}, flash=controller_flash())
        self.assertEqual(status, 409)
        self.assertIn("Home ring", text)

    def test_api_ring_refuses_in_update_mode(self):
        self.assertEqual(self.ring_call({"level": 2}, mode="boot")[0], 409)

    def test_firmware_endpoint_reports_the_ring_level(self):
        built = recipes.build(STOCK_A, ["ring_5"], **K)
        flash = bytearray(controller_flash(built))
        flash[image.RING_SAVED] = 0x21  # 25 %, saved while 5 % was installed
        info = transport.DeviceInfo(0x045E, 0x028E, 0xFF7A, "USB", "x", None)
        with mock.patch.object(cli, "find", lambda: [devices.Found(info, "cable_360")]), \
                mock.patch.object(cli, "open_channel", lambda i, rid: SimApp(bytes(flash))), \
                mock.patch.object(recipes, "_constants", lambda a=None, b=None, c=None: (K["stock_sha256"], K["region_sha256"], K["remainder_sha256"])):
            data = json.loads(self.call("GET", "/api/firmware")[1])
        self.assertEqual(data["ring_level"], 1)

    def test_token_required(self):
        self.assertEqual(self.call("GET", "/api/state", token=None)[0], 403)
        self.assertEqual(self.call("GET", "/api/state", token="wrong")[0], 403)
        self.assertEqual(self.call("GET", "/api/state")[0], 200)

    def test_patch_refused_before_accepting_the_disclaimer(self):
        status, text = self.call("POST", "/api/patch", {"tweaks": ["cable_360"], "base": "backup", "write": False})
        self.assertEqual(status, 403)
        self.assertIn("Accept the disclaimer first.", text)

    def test_accept_is_remembered(self):
        self.assertFalse(json.loads(self.call("GET", "/api/state")[1])["accepted"])
        self.assertEqual(self.call("POST", "/api/accept")[0], 200)
        self.assertTrue(state.accepted(self.store))
        self.assertTrue(json.loads(self.call("GET", "/api/state")[1])["accepted"])

    def test_progress_arrives_in_order_and_ends_with_done(self):
        def fake(args, store):
            args.say("starting")
            args.progress("write", 50, 100)
            args.progress("write", 100, 100)
        jobs.ACTIONS["backup"] = fake
        self.assertEqual(self.call("POST", "/api/backup")[0], 202)
        ev = self.events()
        self.assertEqual([e["type"] for e in ev], ["log", "progress", "progress", "done"])
        self.assertEqual(ev[2], {"type": "progress", "label": "write", "done": 100, "total": 100})

    def test_command_line_hints_stay_out_of_the_app(self):
        def fake(args, store):
            args.say("The check passed.")
            args.hint("Add --write to install.")
        jobs.ACTIONS["backup"] = fake
        self.assertEqual(self.call("POST", "/api/backup", {})[0], 202)
        ev = self.events()
        self.assertEqual(ev[-1]["type"], "done")
        self.assertEqual([e["text"] for e in ev if e["type"] == "log"], ["The check passed."])

    def test_patch_and_restore_pass_their_parameters_to_the_job(self):
        seen = {}

        def fake(args, store):
            seen.update(tweaks=args.tweaks, write=args.write, download=args.download, source=args.source,
                        force_unknown=args.force_unknown)
        state.accept(self.store)
        jobs.ACTIONS["patch"] = fake
        jobs.ACTIONS["restore"] = fake
        self.assertEqual(self.call("POST", "/api/patch", {"tweaks": ["bt_xbox", "cable_360"], "base": "download", "write": True})[0], 202)
        self.events()
        self.assertEqual(seen, dict(tweaks="bt_xbox,cable_360", write=True, download=True, source="backup", force_unknown=False))
        self.assertEqual(self.call("POST", "/api/restore", {"source": "stock", "write": False})[0], 202)
        self.events()
        self.assertEqual((seen["source"], seen["download"], seen["write"], seen["force_unknown"]), ("stock", True, False, False))
        self.call("POST", "/api/restore", {"source": "stock", "write": True, "force_unknown": True})
        self.events()
        self.assertTrue(seen["force_unknown"])

    def test_errors_become_error_events(self):
        def fake(args, store):
            raise RuntimeError("boom")
        jobs.ACTIONS["backup"] = fake
        self.call("POST", "/api/backup")
        ev = self.events()
        self.assertEqual(ev[-1]["type"], "error")
        self.assertIn("boom", ev[-1]["message"])

    def test_second_job_while_busy_is_409(self):
        release = threading.Event()
        jobs.ACTIONS["backup"] = lambda args, store: release.wait(5)
        self.assertEqual(self.call("POST", "/api/backup")[0], 202)
        self.assertEqual(self.call("POST", "/api/backup")[0], 409)
        release.set()
        self.events()

    def test_firmware_endpoint_names_the_tweaks(self):
        built = recipes.build(STOCK_A, ["bt_xbox", "cable_360"], **K)
        info = transport.DeviceInfo(0x2DC8, 0x310A, 0xFF7A, "USB", "x", None)
        with mock.patch.object(cli, "find", lambda: [devices.Found(info, "cable")]), \
                mock.patch.object(cli, "open_channel", lambda i, rid: SimApp(controller_flash(built))), \
                mock.patch.object(recipes, "_constants", lambda a=None, b=None, c=None: (K["stock_sha256"], K["region_sha256"], K["remainder_sha256"])):
            status, text = self.call("GET", "/api/firmware")
        data = json.loads(text)
        self.assertEqual(status, 200, text)
        self.assertTrue(data["known"])
        self.assertEqual(data["recipes"], ["bt_xbox", "cable_360"])
        self.assertIn("Xbox Series X|S controller over Bluetooth", " ".join(data["titles"]))
        self.assertEqual((data["version"], data["version_from"]), (1.09, "update record"))
        self.assertEqual((data["pending"], data["boot_identity"]), (False, None))
        self.assertEqual([(t["key"], t["on"]) for t in data["tweaks"]],
                         [("bt_xbox", True), ("bt_rumble", False), ("cable_360", True), ("dim_leds", False), ("battery_alerts", False), ("ring", False)])

    def test_firmware_endpoint_with_only_bluetooth_explains(self):
        info = transport.DeviceInfo(0x045E, 0x0B13, 1, "Bluetooth Low Energy", "x", None)
        with mock.patch.object(cli, "find", lambda: [devices.Found(info, "bluetooth_xbox")]):
            data = json.loads(self.call("GET", "/api/firmware")[1])
        self.assertEqual(data["note"], "The controller firmware cannot be read over Bluetooth. Connect the controller by cable for firmware diagnostics.")

    def test_firmware_endpoint_is_refused_while_a_job_runs(self):
        release = threading.Event()
        jobs.ACTIONS["backup"] = lambda args, store: release.wait(5)
        self.call("POST", "/api/backup")
        self.assertEqual(self.call("GET", "/api/firmware")[0], 409)
        release.set()
        self.events()

    def test_no_job_starts_while_the_firmware_is_being_read(self):
        reading, release = threading.Event(), threading.Event()

        def slow_read(ch, mode):
            reading.set()
            release.wait(5)
            return probe.Firmware(recipes.State(True, ()), 1.09, "update record")
        info = transport.DeviceInfo(0x2DC8, 0x310A, 0xFF7A, "USB", "x", None)
        jobs.ACTIONS["backup"] = lambda args, store: None
        with mock.patch.object(cli, "find", lambda: [devices.Found(info, "cable")]), \
                mock.patch.object(cli, "open_channel", lambda i, rid: SimApp(controller_flash())), \
                mock.patch.object(probe, "read_firmware", slow_read):
            t = threading.Thread(target=self.call, args=("GET", "/api/firmware"), daemon=True)
            t.start()
            self.assertTrue(reading.wait(5))
            self.assertEqual(self.call("POST", "/api/backup")[0], 409)   # the device is in use
            release.set()
            t.join(5)
            self.assertEqual(self.call("POST", "/api/backup")[0], 202)   # free again
            self.events()

    def test_malformed_json_is_a_400_not_a_dropped_connection(self):
        for raw in (b"{not json", b"[1, 2]"):
            req = urllib.request.Request(self.base + "/api/accept", method="POST", data=raw, headers={"X-Token": self.token})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(e.exception.code, 400)
            e.exception.close()

    def test_running_and_the_end_event_change_together(self):
        runner = jobs.Runner(self.store)
        jobs.ACTIONS["backup"] = lambda args, store: None
        bad = []
        stop = threading.Event()

        def sample():
            while not stop.is_set():
                with runner.cond:
                    last = runner.events[-1]["type"] if runner.events else None
                    terminal = last in ("done", "error")
                    if (terminal and runner.running) or (runner.events and not terminal and not runner.running):
                        bad.append((last, runner.running))   # finished without its end event, or an end event while running
        t = threading.Thread(target=sample, daemon=True)
        t.start()
        for _ in range(200):
            while not runner.start("backup"):
                pass
            with runner.cond:
                runner.cond.wait_for(lambda: runner.events and runner.events[-1]["type"] in ("done", "error"), timeout=5)
        stop.set(); t.join()
        self.assertEqual(bad, [])

    def test_wrong_host_header_is_refused(self):
        req = urllib.request.Request(self.base + "/api/state", headers={"X-Token": self.token, "Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(e.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
