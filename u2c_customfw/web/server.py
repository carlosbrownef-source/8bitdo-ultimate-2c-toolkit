# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP server bound to 127.0.0.1 on a random port. API calls need the session token in X-Token; the Host header must
be this address (against DNS rebinding)."""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__, disclaimer, settings, state
from .. import cli
from ..firmware import recipes
from ..ops import backup as bkp, probe, report as report_mod
from ..ops import settings as settings_ops
from ..ops.plan import OpError
from ..protocol import ProtocolError, app
from ..transport import PermissionDenied
from . import jobs

STATIC = Path(__file__).parent / "static"
SETTINGS_MISSING = "To change these settings, install Controller settings in the Firmware tab."
KEEPALIVE_S = 15
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
            route = {"/api/state": self.api_state, "/api/events": self.api_events, "/api/firmware": self.api_firmware,
                     "/api/settings": self.api_settings_read, "/api/busy": self.api_busy}.get(path)
            if route:
                return route()
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
                                       "backups": backups,
                                       "disclaimer": disclaimer.text()}))

        def api_busy(self):
            """For the Mac app's quit and close guard: the server knows, even when the page has lost track."""
            if self.auth():
                self.send(200, json.dumps({"writing": runner.writing}))

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

            def work(ch):
                if app.read(ch, recipes.RING_CODE[0], 4) in (None, b"\xff" * 4):
                    raise OpError("Install a Home ring brightness in Tweaks first.")
                if level is not None:
                    app.set_ring(ch, level)
                if save:
                    app.save_ring(ch)
                return {"ok": True}

            self.by_cable(work)

        def by_cable(self, work):
            """Runs work(channel) on the one controller connected by cable, holding the device, and sends its answer."""
            if not runner.claim():
                return self.send(409, json.dumps({"error": "Another task is running."}))
            try:
                ours = [f for f in cli.find() if f.mode in ("cable", "cable_360")]
                if len(ours) != 1:
                    return self.send(409, json.dumps({"error": "Connect the controller by cable, without other controllers."}))
                ch = cli.open_channel(ours[0].info, 0x81)
                try:
                    if app.open_session(ch) is None:
                        raise OpError(settings_ops.NO_ANSWER)
                    probe.check_not_dongle(ch)
                    answer = work(ch)
                finally:
                    ch.close()
                self.send(200, json.dumps(answer))
            except (OpError, PermissionDenied, OSError) as e:
                self.send(409, json.dumps({"error": str(e)}))
            finally:
                runner.release()

        def api_settings_read(self):
            """Always answers with the fields, which the page builds its controls from, and says if they can be changed now."""
            if not self.auth():
                return
            fields = [{"name": f.name, "low": f.low, "high": f.high, "default": f.default, "choices": list(f.choices) if f.choices else None}
                      for f in settings.FIELDS]
            for f in fields:
                if f["choices"] is None:
                    del f["choices"]

            def answer(**rest):
                self.send(200, json.dumps({"fields": fields, "available": False, "note": "", **rest}))

            if not runner.claim():
                return answer(note="Another task is running.")
            try:
                ours = [f for f in cli.find() if f.mode in ("cable", "cable_360")]
                if len(ours) != 1:
                    return answer(note="Connect the controller by cable to change these settings.")
                ch = cli.open_channel(ours[0].info, 0x81)
                try:
                    if app.open_session(ch) is None:
                        return answer(note=settings_ops.NO_ANSWER)
                    probe.check_not_dongle(ch)
                    if not settings_ops.installed(ch):
                        return answer(note=SETTINGS_MISSING)
                    answer(available=True, **settings_ops.load(ch))
                finally:
                    ch.close()
            except (OpError, PermissionDenied, OSError) as e:
                answer(note=str(e))
            finally:
                runner.release()

        def api_settings(self, req):
            """One request: change fields, a mapping or the dead zone switch, save, or reset."""
            changes, mapping, dead_zone = req.get("set"), req.get("mapping"), req.get("dead_zone_off")
            values, save, reset = req.get("values"), req.get("save") is True, req.get("reset") is True
            good = sum(x is not None for x in (changes, mapping, dead_zone)) + save + reset == 1
            if changes is not None:
                good = good and isinstance(changes, dict) and bool(changes) and all(settings.valid(n, v) for n, v in changes.items())
            if mapping is not None:
                good = good and isinstance(mapping, dict) and mapping.get("slot") in ("r4", "l4") and type(mapping.get("mask")) is int \
                    and mapping["mask"] >= 0 and not mapping["mask"] & ~settings.MAP_MASK
            if dead_zone is not None:
                good = good and type(dead_zone) is bool
            if save:
                good = good and isinstance(values, dict) and set(values) == set(settings.BY_NAME) and all(settings.valid(n, v) for n, v in values.items())
                kept_map, kept_dz = req.get("kept_mapping"), req.get("kept_dead_zone_off")
                good = good and (kept_dz is None or type(kept_dz) is bool) and (kept_map is None or (
                    isinstance(kept_map, dict) and set(kept_map) == {"r4", "l4"}
                    and all(type(m) is int and 0 <= m <= settings.MAP_MASK for m in kept_map.values())))
            if not good:
                return self.send(400, json.dumps({"error": "bad request"}))

            def work(ch):
                if not settings_ops.installed(ch):
                    raise OpError(SETTINGS_MISSING)
                if changes is not None:
                    settings_ops.change(ch, changes)
                elif mapping is not None:
                    app.set_mapping(ch, 1 if mapping["slot"] == "l4" else 0, mapping["mask"])
                elif dead_zone is not None:
                    app.set_dead_zone(ch, dead_zone)
                elif save and not settings_ops.save(ch, values, kept_map, kept_dz):
                    raise OpError("The controller didn't confirm the save. Check the cable and try again.")
                elif reset:
                    return {"ok": True, "values": settings_ops.reset(ch)}
                settings_ops.still_there(ch)
                return {"ok": True}

            self.by_cable(work)

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
                    pick = bkp.restorable(cli.unit_backups(ch, store)) if f.mode == "boot" else None   # what Restore your backup would use
                finally:
                    ch.close()
                st, version = fw.state, fw.version
            except (OpError, PermissionDenied, OSError, ProtocolError) as e:
                return self.send(200, json.dumps({"error": str(e)}))
            ring = [recipes.RECIPES[k].title for k in st.recipes if recipes.RECIPES[k].group == "ring"]
            self.send(200, json.dumps({"known": st.known, "recipes": list(st.recipes), "version": version, "version_from": fw.version_from,
                                       "pending": fw.pending, "boot_identity": fw.boot_identity, "outdated": st.outdated, "ring_level": fw.ring_level,
                                       "restore_backup": pick and {"name": pick.path.name, "taken": bkp.taken(pick.path), "firmware": bkp.describe(pick.state)},
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
                    if i >= len(runner.events):
                        runner.cond.wait(timeout=KEEPALIVE_S)
                    batch = runner.events[i:]
                if not batch:   # written outside the lock, so a client that stops reading can't hold up the job
                    self.wfile.write(b": keepalive\n\n"); self.wfile.flush()
                    continue
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
            if route == "/api/settings":
                return self.api_settings(req)
            if route == "/api/report":
                return self.send(200, json.dumps({"text": report_mod.report(cli.find(), None, report_mod.log_tail(store), report_mod.clean_extras(req))}))
            if route in ("/api/patch", "/api/restore") and not state.accepted(store):
                return self.send(403, json.dumps({"error": "Accept the disclaimer first."}))
            params = {"/api/backup": ("backup", {}),
                      "/api/patch": ("patch", dict(tweaks=",".join(req.get("tweaks", [])), download=req.get("base") == "download",
                                                    write=bool(req.get("write")))),
                      "/api/restore": ("restore", dict(source=req.get("source", "backup"), write=bool(req.get("write")),
                                                        expect=req.get("backup") if isinstance(req.get("backup"), str) else None,
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
