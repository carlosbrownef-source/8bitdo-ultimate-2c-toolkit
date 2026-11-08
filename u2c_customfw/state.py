# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-user state: where things live, and whether the disclaimer has been accepted."""
import fcntl
import sys
from pathlib import Path


def default_store() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "u2c-customfw"
    return Path.home() / ".local" / "share" / "u2c-customfw"


def accepted(store: Path) -> bool:
    return (Path(store) / "disclaimer-accepted").exists()


def accept(store: Path) -> None:
    Path(store).mkdir(parents=True, exist_ok=True)
    (Path(store) / "disclaimer-accepted").write_text("accepted\n")


def lock_device(store: Path):
    """Taken while a front end uses the controller, so two of them (the app and the command line, say) can't interleave
    their requests. The open lock file, or None if another process holds it."""
    Path(store).mkdir(parents=True, exist_ok=True)
    f = open(Path(store) / "device.lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def unlock_device(lock) -> None:
    lock.close()
