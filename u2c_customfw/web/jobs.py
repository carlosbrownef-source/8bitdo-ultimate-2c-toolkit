# SPDX-License-Identifier: GPL-3.0-or-later
"""One background job at a time, with an append-only event list that Server-Sent Events replay."""
import threading
from types import SimpleNamespace

from .. import cli, fetch
from ..ops.plan import OpError
from ..transport import PermissionDenied

# job name -> function(args, store); tests replace entries
ACTIONS = {"backup": cli.cmd_backup, "patch": cli.cmd_patch, "restore": cli.cmd_restore}


class Runner:
    def __init__(self, store):
        self.store, self.events, self.running = store, [], False
        self.cond = threading.Condition()

    def push(self, event: dict) -> None:
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def start(self, name: str, **params) -> bool:
        with self.cond:
            if self.running:
                return False
            self.running, self.events = True, []
        args = SimpleNamespace(**{**dict(write=False, tweaks="", backup=None, download=False, source="backup", file=None,
                                         accept_disclaimer=False, force_unknown=False), **params})
        args.say = lambda text: self.push({"type": "log", "text": str(text)})
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
        with self.cond:
            self.events.append(end)
            self.running = False
            self.cond.notify_all()
