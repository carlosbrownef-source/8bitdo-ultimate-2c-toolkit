# SPDX-License-Identifier: GPL-3.0-or-later
"""One background job at a time, with an append-only event list that Server-Sent Events replay."""
import threading
from types import SimpleNamespace

from .. import cli, fetch, state
from ..ops.log import get_logger
from ..ops.plan import OpError
from ..transport import PermissionDenied

# job name -> function(args, store); tests replace entries
ACTIONS = {"backup": cli.cmd_backup, "patch": cli.cmd_patch, "restore": cli.cmd_restore}


class Runner:
    def __init__(self, store):
        self.store, self.events, self.running, self.lock = store, [], False, None
        self.writing = False   # a job that writes to the controller is running: the Mac app asks before quitting
        self.cond = threading.Condition()

    def push(self, event: dict) -> None:
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def _take(self) -> bool:
        """With self.cond held: the device for this server, unless a job here or another process is using it."""
        if self.running:
            return False
        self.lock = state.lock_device(self.store)
        self.running = self.lock is not None
        return self.running

    def _free(self) -> None:
        state.unlock_device(self.lock)
        self.running = self.writing = False
        self.cond.notify_all()

    def claim(self) -> bool:
        """Take the device for a short read outside the job system (the firmware read); False if it is in use."""
        with self.cond:
            return self._take()

    def release(self) -> None:
        with self.cond:
            self._free()

    def start(self, name: str, **params) -> bool:
        with self.cond:
            if not self._take():
                return False
            self.events, self.writing = [], bool(params.get("write"))
        args = SimpleNamespace(**{**dict(write=False, tweaks="", backup=None, download=False, source="backup", expect=None,
                                         accept_disclaimer=False, force_unknown=False), **params})
        log = get_logger(self.store)
        log.info("job %s %s", name, params)   # the page never sends a path

        def say(text):
            log.info("  %s", text)
            self.push({"type": "log", "text": str(text)})
        args.say = say
        args.hint = lambda text: None  # command-line advice, meaningless in the app
        args.progress = lambda label, done, total: self.push({"type": "progress", "label": label, "done": done, "total": total})
        threading.Thread(target=self._run, args=(name, args), daemon=True).start()
        return True

    def _run(self, name, args):
        try:
            ACTIONS[name](args, self.store)
            end = {"type": "done"}
        except cli.Exit as e:
            end = {"type": "error", "message": e.msg}
        except (OpError, fetch.FetchError, PermissionDenied) as e:
            end = {"type": "error", "message": str(e)}
        except Exception as e:  # shown to the user, never a hang
            end = {"type": "error", "message": f"{type(e).__name__}: {e}"}
        get_logger(self.store).info("done" if end["type"] == "done" else f"error: {end['message']}")
        with self.cond:
            self.events.append(end)
            self._free()
