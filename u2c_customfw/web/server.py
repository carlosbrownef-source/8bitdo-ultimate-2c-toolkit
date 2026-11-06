# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP server bound to 127.0.0.1 on a random port. API calls need the session token in X-Token; the Host header must
be this address (against DNS rebinding)."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__, disclaimer, state
from .. import cli
from ..firmware import recipes
from ..ops import probe, report as report_mod
from ..ops.plan import OpError
from ..protocol import app
from ..transport import PermissionDenied
from . import jobs

STATIC = Path(__file__).parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}


def make_server(store: Path, port: int = 0):
    token = secrets.token_urlsafe(24)
    runner = jobs.Runner(store)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def host_ok(self):
            return self.headers.get("Host", "") in (f"127.0.0.1:{self.server.server_address[1]}", f"localhost:{self.server.server_address[1]}")

        def auth(self):
            given = self.headers.get("X-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
            if not self.host_ok() or not secrets.compare_digest(given, token):
                self.send(403, json.dumps({"error": "forbidden"}))
                return False
            return True

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if not self.host_ok():
                return self.send(403, "forbidden", "text/plain")
            path = self.path.split("?")[0]
            if path == "/api/state":
                return self.api_state()
            if path == "/api/events":
                return self.api_events()
            if path == "/api/firmware":
                return self.api_firmware()
            name = "index.html" if path == "/" else path.lstrip("/").removeprefix("static/")
            f = (STATIC / name).resolve()
            if f.parent == STATIC.resolve() and f.is_file():
                return self.send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
            self.send(404, "not found", "text/plain")

        def api_state(self):
            if not self.auth():
                return
            found = []
            try:
                found = [{"mode": f.mode, "vendor": f.info.vendor, "product": f.info.product, "name": f.info.name}
                         for f in cli.find()]
            except Exception as e:
                found = [{"mode": "error", "name": str(e)}]
            backups = sorted(p.name for p in Path(store).glob("controller-*.bin"))
            self.send(200, json.dumps({"version": __version__, "accepted": state.accepted(store), "devices": found,
                                       "backups": backups, "busy": runner.running,
                                       "disclaimer": disclaimer.text()}))

        def api_firmware(self):
            """Read the connected controller's bank A (read-only) and name its firmware and tweaks."""
            if not self.auth():
                return
            if not runner.claim():   # one user of the device at a time: no job may start during this read
                return self.send(409, json.dumps({"error": "Another task is running."}))
            try:
                self.firmware_report()
            finally:
                runner.release()

        def api_ring(self, req):
            """The Home ring's live level or save, by cable; over Bluetooth the Mac app sends them itself."""
            level, save = req.get("level"), req.get("save") is True
            if (level is None and not save) or (level is not None and (type(level) is not int or not 0 <= level < len(recipes.RING_ORDER))):
                return self.send(400, json.dumps({"error": "bad request"}))
            if not runner.claim():
                return self.send(409, json.dumps({"error": "Another task is running."}))
            try:
                ours = [f for f in cli.find() if f.mode in ("cable", "cable_360")]
                if len(ours) != 1:
                    return self.send(409, json.dumps({"error": "Connect the controller by cable, without other controllers."}))
                ch = cli.open_channel(ours[0].info, 0x81)
                try:
                    if app.open_session(ch) is None or app.read(ch, recipes.RING_CODE[0], 4) in (None, b"\xff" * 4):
                        return self.send(409, json.dumps({"error": "Install a Home ring brightness in Tweaks first."}))
                    if level is not None:
                        app.set_ring(ch, level)
                    if save:
                        app.save_ring(ch)
                finally:
                    ch.close()
                self.send(200, json.dumps({"ok": True}))
            except (OpError, PermissionDenied, OSError) as e:
                self.send(409, json.dumps({"error": str(e)}))
            finally:
                runner.release()

        def firmware_report(self):
            found = cli.find()
            ours = [f for f in found if f.mode in cli.CONTROLLER_MODES]
            if len(ours) > 1:
                return self.send(200, json.dumps({"error": "More than one device is connected. Unplug all but one controller."}))
            if not ours:
                note = "Connect it by cable, or put it in update mode."
                if any(f.mode.startswith("bluetooth") for f in found):
                    note = "The controller firmware cannot be read over Bluetooth. Connect the controller by cable for firmware diagnostics."
                return self.send(200, json.dumps({"note": note}))
            f = ours[0]
            if f.mode == "dongle":
                return self.send(200, json.dumps({"error": "That is the 2.4 GHz dongle, which this app does not support."}))
            try:
                ch = cli.open_channel(f.info, 0 if f.mode == "boot" else 0x81)
                try:
                    fw = probe.read_firmware(ch, f.mode)
                finally:
                    ch.close()
                st, version = fw.state, fw.version
            except (OpError, PermissionDenied, OSError) as e:
                return self.send(200, json.dumps({"error": str(e)}))
            ring = [recipes.RECIPES[k].title for k in st.recipes if recipes.RECIPES[k].group == "ring"]
            self.send(200, json.dumps({"mode": f.mode, "known": st.known, "recipes": list(st.recipes), "version": version, "version_from": fw.version_from,
                                       "pending": fw.pending, "boot_identity": fw.boot_identity, "outdated": st.outdated, "ring_level": fw.ring_level,
                                       "titles": [recipes.RECIPES[k].title for k in st.recipes],
                                       "tweaks": [{"key": k, "title": r.title, "on": k in st.recipes}
                                                  for k, r in recipes.RECIPES.items() if not r.group]
                                                 + [{"key": "ring", "title": ring[0] if ring else "Home ring: normal", "on": bool(ring)}]}))

        def api_events(self):
            if not self.auth():
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            i = 0
            while True:
                with runner.cond:
                    while i >= len(runner.events):
                        if not runner.cond.wait(timeout=15):
                            self.wfile.write(b": keepalive\n\n"); self.wfile.flush()
                    batch = runner.events[i:]
                i += len(batch)
                for e in batch:
                    self.wfile.write(f"data: {json.dumps(e)}\n\n".encode())
                self.wfile.flush()
                if batch[-1]["type"] in ("done", "error"):
                    return

        def do_POST(self):
            if not self.auth():
                return
            try:
                req = self.body()
                if not isinstance(req, dict):
                    raise ValueError("not an object")
            except ValueError:
                return self.send(400, json.dumps({"error": "bad request"}))
            route = self.path.split("?")[0]
            if route == "/api/accept":
                state.accept(store)
                return self.send(200, json.dumps({"accepted": True}))
            if route == "/api/ring":
                return self.api_ring(req)
            if route == "/api/report":
                log = Path(store) / "u2c-customfw.log"
                tail = "\n".join(log.read_text().splitlines()[-30:]) if log.exists() else ""
                return self.send(200, json.dumps({"text": report_mod.report(cli.find(), None, tail, report_mod.clean_extras(req))}))
            if route in ("/api/patch", "/api/restore") and not state.accepted(store):
                return self.send(403, json.dumps({"error": "Accept the disclaimer first."}))
            params = {"/api/backup": ("backup", {}),
                      "/api/patch": ("patch", dict(tweaks=",".join(req.get("tweaks", [])), download=req.get("base") == "download",
                                                    write=bool(req.get("write")))),
                      "/api/restore": ("restore", dict(source=req.get("source", "backup"), file=req.get("file"),
                                                        download=req.get("source") == "stock", write=bool(req.get("write")),
                                                        force_unknown=bool(req.get("force_unknown"))))}.get(route)
            if params is None:
                return self.send(404, json.dumps({"error": "unknown call"}))
            if not runner.start(params[0], **params[1]):
                return self.send(409, json.dumps({"error": "Another task is running."}))
            self.send(202, json.dumps({"started": params[0]}))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler), token


def serve(store: Path, port: int = 0) -> None:
    httpd, token = make_server(store, port)
    print(f"U2C_URL http://127.0.0.1:{httpd.server_address[1]}/?token={token}", flush=True)
    httpd.serve_forever()
