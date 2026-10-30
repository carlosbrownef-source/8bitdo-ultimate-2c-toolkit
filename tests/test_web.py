# SPDX-License-Identifier: GPL-3.0-or-later
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from u2c_customfw import state
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

    def test_patch_and_restore_pass_their_parameters_to_the_job(self):
        seen = {}

        def fake(args, store):
            seen.update(tweaks=args.tweaks, write=args.write, download=args.download, source=args.source)
        state.accept(self.store)
        jobs.ACTIONS["patch"] = fake
        jobs.ACTIONS["restore"] = fake
        self.assertEqual(self.call("POST", "/api/patch", {"tweaks": ["bt_xbox", "cable_360"], "base": "download", "write": True})[0], 202)
        self.events()
        self.assertEqual(seen, dict(tweaks="bt_xbox,cable_360", write=True, download=True, source="backup"))
        self.assertEqual(self.call("POST", "/api/restore", {"source": "stock", "write": False})[0], 202)
        self.events()
        self.assertEqual((seen["source"], seen["download"], seen["write"]), ("stock", True, False))

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

    def test_wrong_host_header_is_refused(self):
        req = urllib.request.Request(self.base + "/api/state", headers={"X-Token": self.token, "Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(e.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
