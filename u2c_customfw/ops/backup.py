# SPDX-License-Identifier: GPL-3.0-or-later
"""Full read-only backup of the controller's flash, over the cable (update channel) or in boot mode."""
import datetime
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .. import protocol
from ..firmware import image, recipes
from ..protocol import app, boot
from .plan import OpError

CABLE_MODES = ("cable", "cable_360")


@dataclass
class Backup:
    path: Path
    sha256: str
    state: recipes.State
    data: bytes


def _read_all(ch, mode, label, progress) -> bytes:
    size = image.FLASH_SIZE
    if mode == "boot":
        return boot.read(ch, 0, size, lambda d, t: progress(label, d, t))
    out = bytearray()
    for a in range(0, size, boot.CHUNK):
        c = app.read(ch, a, min(boot.CHUNK, size - a))
        if c is None:
            raise OpError(f"the controller did not answer at {a:#x}; nothing was saved")
        out += c
        if len(out) % 0x4000 < boot.CHUNK:
            progress(label, len(out), size)
    return bytes(out)


def _state(data: bytes) -> recipes.State:
    return recipes.identify(data[image.BASE:image.BANK_A_END])


def backup(ch, mode: str, store: Path, progress) -> Backup:
    try:
        if mode in CABLE_MODES:
            if app.open_session(ch) is None:
                raise OpError("the controller does not answer reads: unplug it, plug it back in and try again")
            if app.read(ch, 0x10000, 16) == b"\xff" * 16:
                raise OpError("this looks like the 2.4 GHz dongle, which this app does not support")
        elif mode == "boot" and boot.kind(ch) != "controller":
            raise OpError("the device in boot mode is not a controller (the dongle is not supported)")
        a = _read_all(ch, mode, "pass 1", progress)
        b = _read_all(ch, mode, "pass 2", progress)
    except protocol.ProtocolError as e:
        raise OpError(str(e)) from e
    if a != b:
        n = sum(a[i:i + boot.CHUNK] != b[i:i + boot.CHUNK] for i in range(0, len(a), boot.CHUNK))
        raise OpError(f"the two read passes differ at {n} place(s); nothing was saved. Try again with a good cable.")
    store.mkdir(parents=True, exist_ok=True)
    path = store / f"controller-{datetime.datetime.now():%Y%m%d-%H%M%S}.bin"
    n = 1
    while path.exists():
        path = path.with_name(f"{path.stem.split('+')[0]}+{n}.bin")
        n += 1
    path.write_bytes(a)
    sha = hashlib.sha256(a).hexdigest()
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise OpError(f"{path} does not read back identically")
    with open(store / "SHA256SUMS", "a") as f:
        f.write(f"{sha}  {path.name}\n")
    return Backup(path, sha, _state(a), a)


def load(path: Path) -> Backup:
    data = Path(path).read_bytes()
    if len(data) != image.FLASH_SIZE:
        raise OpError(f"{path} is not a full controller backup ({len(data)} bytes)")
    return Backup(Path(path), hashlib.sha256(data).hexdigest(), _state(data), data)


def find_backups(store: Path, bootloader: bytes, mac: bytes) -> list[Backup]:
    """Backups in the store taken from this unit (same bootloader and MAC sector), newest first."""
    out = []
    for p in sorted(Path(store).glob("controller-*.bin"), reverse=True):
        try:
            b = load(p)
        except (OSError, OpError):
            continue
        if b.data[:image.BOOT_END] == bootloader and b.data[image.MAC_SECTOR:image.MAC_SECTOR + image.SECTOR] == mac:
            out.append(b)
    return out
