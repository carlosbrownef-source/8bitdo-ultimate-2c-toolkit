# SPDX-License-Identifier: GPL-3.0-or-later
"""Full read-only backup of the controller's flash, over the cable (update channel) or in boot mode."""
import datetime
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .. import protocol
from ..firmware import image, recipes
from ..protocol import boot
from . import probe, shown
from .plan import OpError

CABLE_MODES = ("cable", "cable_360")


@dataclass
class Backup:
    path: Path
    sha256: str
    state: recipes.State
    data: bytes


def _state(data: bytes) -> recipes.State:
    return recipes.identify(data[image.BASE:image.APP_END])


def backup(ch, mode: str, store: Path, progress) -> Backup:
    try:
        if mode in CABLE_MODES or mode == "boot":
            probe._check_device(ch, mode, boot.identify(ch) if mode == "boot" else None)
        size = image.FLASH_SIZE
        a = probe._read(ch, mode, 0, size, lambda d, t: progress("pass 1", d, t))
        b = probe._read(ch, mode, 0, size, lambda d, t: progress("pass 2", d, t))
    except protocol.ProtocolError as e:
        raise OpError(str(e)) from e
    if a != b:
        n = sum(a[i:i + boot.CHUNK] != b[i:i + boot.CHUNK] for i in range(0, len(a), boot.CHUNK))
        raise OpError(f"The two reads of the controller's memory differ in {n} place(s), so nothing was saved. Try again with another cable.")
    store.mkdir(parents=True, exist_ok=True)
    path = store / f"controller-{datetime.datetime.now():%Y%m%d-%H%M%S}.bin"
    n = 1
    while path.exists():
        path = path.with_name(f"{path.stem.split('+')[0]}+{n}.bin")
        n += 1
    path.write_bytes(a)
    sha = hashlib.sha256(a).hexdigest()
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise OpError(f"{path} didn't read back identically.")
    with open(store / "SHA256SUMS", "a") as f:
        f.write(f"{sha}  {path.name}\n")
    return Backup(path, sha, _state(a), a)


def load(path: Path) -> Backup:
    data = Path(path).read_bytes()
    if len(data) != image.FLASH_SIZE:
        raise OpError(f"{path} isn't a full backup of the controller ({len(data)} bytes).")
    return Backup(Path(path), hashlib.sha256(data).hexdigest(), _state(data), data)


def _stored(store: Path):
    for p in sorted(Path(store).glob("controller-*.bin"), reverse=True):
        try:
            yield load(p)
        except (OSError, OpError):
            continue


def find_backups(store: Path, bootloader: bytes, mac: bytes) -> list[Backup]:
    """Backups in the store taken from this unit (same bootloader and address), newest first."""
    return [b for b in _stored(store) if b.data[:image.BOOT_END] == bootloader
            and image.same_unit(b.data[image.MAC_SECTOR:image.MAC_SECTOR + image.SECTOR], mac)]


def restorable(backups: list[Backup]) -> Backup | None:
    """The one Restore your backup uses: the newest whose firmware the app recognises, never a damaged or foreign one."""
    return next((b for b in backups if b.state.known), None)


def taken(path: Path) -> str:
    """When a backup was made, from its name (controller-YYYYMMDD-HHMMSS.bin), or else from the file."""
    m = re.match(r"controller-(\d{8}-\d{6})", Path(path).name)
    d = datetime.datetime.strptime(m.group(1), "%Y%m%d-%H%M%S") if m else datetime.datetime.fromtimestamp(Path(path).stat().st_mtime)
    return f"{d.day} {d:%b %Y} at {d:%H:%M}"


def describe(state: recipes.State) -> str:
    """The firmware in words: "the original firmware 1.09", "firmware 1.09 with A and B", or that it isn't recognised."""
    if not state.known:
        return "firmware this app doesn't recognise"
    titles = [recipes.RECIPES[k].title for k in shown(state.recipes)]
    if not titles:
        return "the original firmware 1.09"
    return "firmware 1.09 with " + (titles[0] if len(titles) == 1 else f"{', '.join(titles[:-1])} and {titles[-1]}")


def find_original(backup: Backup, store: Path) -> bytes | None:
    """The original firmware from this backup or any other, in bank A or in bank B. It's the same for every controller."""
    for b in (backup, *_stored(store)):
        for start in (image.BASE, image.BANK_B):
            bank = b.data[start:start + image.BANK_A_SIZE]
            s = recipes.identify(bank)
            if s.known and not s.recipes:
                return bank
    return None
