# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the connected controller (read-only): which firmware it holds, its version, and which tweaks are applied."""
from dataclasses import dataclass

from .. import protocol
from ..firmware import image, recipes
from ..protocol import app, boot
from .plan import OpError



@dataclass
class Firmware:
    state: recipes.State
    version: float | None
    version_from: str   # "update record", "bank A hash", "bank B hash" or "unknown"
    pending: bool = False
    boot_identity: int | None = None   # only in update mode; None if the bootloader doesn't answer


def _read(ch, mode: str, addr: int, n: int) -> bytes:
    if mode == "boot":
        return boot.read(ch, addr, n)
    out = bytearray()
    for a in range(addr, addr + n, boot.CHUNK):
        c = app.read(ch, a, min(boot.CHUNK, addr + n - a))
        if c is None:
            raise OpError(f"The controller didn't answer at {a:#x}.")
        out += c
    return bytes(out)


def _check_device(ch, mode: str, identity: int | None) -> None:
    if mode == "boot":
        if boot.kind_from(ch, identity) != "controller":
            raise OpError("The device in update mode isn't a controller. The 2.4 GHz dongle isn't supported.")
        return
    if app.open_session(ch) is None:
        raise OpError("The controller isn't answering. Unplug it, plug it back in and try again.")
    if app.read(ch, 0x10000, 16) == b"\xff" * 16:
        raise OpError("This looks like the 2.4 GHz dongle, which this app doesn't support.")


def pending_update(ch, mode: str) -> bool:
    """Whether the update record holds a staged update (+0x18 magic, +0x20 length; zero or blank means none)."""
    record = _read(ch, mode, image.UPDATE_RECORD, 0x24)
    return any(f not in (bytes(4), b"\xff" * 4) for f in (record[0x18:0x1C], record[0x20:0x24]))


def parse_version(record: bytes) -> float | None:
    """Firmware version from the update record (byte +0x0c is the version times 100), or None if it is blank."""
    v = record[0x0C] if len(record) > 0x0C else 0
    return None if v in (0, 0xFF) else v / 100


def detect_version(ch, mode: str, bank_a: bytes | None = None) -> tuple[float | None, str]:
    """The firmware version and where it was read from: the update record if it has one; otherwise 1.09 when bank A
    (or else bank B, the second app copy) is, by hash, stock v1.09 or one of our builds; otherwise unknown."""
    try:
        v = parse_version(_read(ch, mode, image.UPDATE_RECORD, 16))
        if v is not None:
            return v, "update record"
        if bank_a is None:
            bank_a = _read(ch, mode, image.BASE, image.BANK_A_SIZE)
        if recipes.identify(bank_a).known:
            return image.SUPPORTED_VERSION, "bank A hash"
        if recipes.identify(_read(ch, mode, image.BANK_B, image.BANK_A_SIZE)).known:
            return image.SUPPORTED_VERSION, "bank B hash"
    except protocol.ProtocolError as e:
        raise OpError(str(e)) from e
    return None, "unknown"


def read_firmware(ch, mode: str) -> Firmware:
    identity = boot.identify(ch) if mode == "boot" else None
    try:
        _check_device(ch, mode, identity)
        bank_a = _read(ch, mode, image.BASE, image.BANK_A_SIZE)
        pending = pending_update(ch, mode)
    except protocol.ProtocolError as e:
        raise OpError(str(e)) from e
    version, how = detect_version(ch, mode, bank_a)
    return Firmware(recipes.identify(bank_a), version, how, pending, identity)


def read_state(ch, mode: str) -> recipes.State:
    return read_firmware(ch, mode).state
