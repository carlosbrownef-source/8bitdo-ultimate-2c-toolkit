# SPDX-License-Identifier: GPL-3.0-or-later
"""The 2.4 GHz dongle: read its firmware, back it up, and write its bank A with the Xbox 360 change or without it.

Reads are the controller's `81 05 05` (protocol/app.py), idle (2dc8:301c) or paired. A write follows the stream proven on
this dongle (docs, dongle-analysis): `81 05 00 51 00` on the idle dongle, which restarts it into its bootloader
(2dc8:3208, identity 0x301c); there, the bootloader must match the backup; erase 0x6000-0x10000, write all but the first
46 bytes, which hold the app header, read back, write the header last, read the whole bank back, restart with cmd 7. If
anything stops before the header is written, the bootloader finds no app and stays in update mode, where Restore works.
Nothing outside bank A is ever written: the update record, bank B, the calibration and the licence sector stay as they are."""
import datetime
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from .. import protocol
from ..protocol import app, boot
from .plan import OpError
from .probe import parse_version

BASE, SIZE = 0x6000, 0xA000   # bank A: the whole application
END = BASE + SIZE
FLASH, BOOT_END, CAL = 0x20000, 0x6000, 0x1E000   # the whole part, the bootloader, a few unit-specific calibration bytes
RECORD = 0x12000              # the update record; the version times 100 at +0x0c
STOCK_SHA256 = "15caaa7c705629c768dc7c22417abf047cb06b499376c5c8b8fe14c0f606028c"     # 8BitDo's v1.03
XBOX360_SHA256 = "3c09da195ae59a7dee63c54621b64afca5fa5dfe131989d655f1acb284c6cbd5"   # v1.03 presenting as a wired Xbox 360 pad, bcdDevice 0x0103
CHUNK = 46                    # the largest read the dongle answers
DESC = 0xF1A0                 # the X-input device descriptor: the only bytes the Xbox 360 change touches
STOCK_DESC = bytes.fromhex("12 01 00 02 00 00 00 08 c8 2d 0a 31 14 01 01 02 03 01")
XBOX_DESC = bytes.fromhex("12 01 00 02 ff ff ff 08 5e 04 8e 02 03 01 01 02 03 01")   # 045e:028e, class ff, bcdDevice 0x0103
TITLE = "Xbox 360 controller over 2.4 GHz"


@dataclass
class DongleFirmware:
    known: bool
    version: float | None
    xbox360: bool


def _read(ch, addr: int, n: int, progress=None) -> bytes:
    out = bytearray()
    for a in range(addr, addr + n, CHUNK):
        c = app.read(ch, a, min(CHUNK, addr + n - a))
        if c is None:
            raise OpError(f"The dongle didn't answer at {a:#x}. Unplug it, plug it back in and try again.")
        out += c
        if progress and len(out) % 0x2000 < CHUNK:
            progress(len(out), n)
    return bytes(out)


def state(bank: bytes, stock_sha256: str | None = None, xbox360_sha256: str | None = None) -> tuple[bool, bool]:
    """(known, with the Xbox 360 change) for a bank A, by hash."""
    h = hashlib.sha256(bank).hexdigest()
    return h in (stock_sha256 or STOCK_SHA256, xbox360_sha256 or XBOX360_SHA256), h == (xbox360_sha256 or XBOX360_SHA256)


def read_firmware(ch, stock_sha256: str | None = None, xbox360_sha256: str | None = None, in_boot: bool = False) -> DongleFirmware:
    """v1.03 as 8BitDo ships it or with the Xbox 360 change, by hash; otherwise the version its update record gives.
    in_boot: ch is the bootloader's channel, for a dongle left in update mode."""
    read = (lambda a, n: boot.read(ch, a, n)) if in_boot else (lambda a, n: _read(ch, a, n))
    try:
        known, xbox = state(read(BASE, SIZE), stock_sha256, xbox360_sha256)
        return DongleFirmware(True, 1.03, xbox) if known else DongleFirmware(False, parse_version(read(RECORD, 16)), False)
    except protocol.ProtocolError as e:
        raise OpError(str(e)) from e


def unit_of(full: bytes) -> bytes:
    """What tells this dongle from another one: its bootloader and its calibration bytes, compared, never shown."""
    return full[:BOOT_END] + full[CAL:CAL + 0x40]


def read_unit(ch, in_boot: bool = False) -> bytes:
    read = (lambda a, n: boot.read(ch, a, n)) if in_boot else (lambda a, n: _read(ch, a, n))
    try:
        return read(0, BOOT_END) + read(CAL, 0x40)
    except protocol.ProtocolError as e:
        raise OpError(str(e)) from e


def backup(ch, store: Path, progress) -> Path:
    """The whole 128 KB read twice, compared, and kept as dongle-YYYYMMDD-HHMMSS.bin."""
    a = _read(ch, 0, FLASH, lambda d, t: progress("pass 1", d, t))
    b = _read(ch, 0, FLASH, lambda d, t: progress("pass 2", d, t))
    if a != b:
        raise OpError("The two reads of the dongle's memory differ, so nothing was saved. Try again in another USB port.")
    store.mkdir(parents=True, exist_ok=True)
    path = store / f"dongle-{datetime.datetime.now():%Y%m%d-%H%M%S}.bin"
    path.write_bytes(a)
    sha = hashlib.sha256(a).hexdigest()
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise OpError(f"{path.name} didn't read back identically.")
    with open(store / "SHA256SUMS", "a") as f:
        f.write(f"{sha}  {path.name}\n")
    return path


def unit_backups(store: Path, unit: bytes) -> list[tuple[Path, bytes]]:
    """This dongle's backups, newest first."""
    out = []
    for p in sorted(Path(store).glob("dongle-*.bin"), reverse=True):
        data = p.read_bytes()
        if len(data) == FLASH and unit_of(data) == unit:
            out.append((p, data))
    return out


def target(bank: bytes, xbox: bool) -> bytes:
    """Bank A with or without the Xbox 360 change, made from a bank the app recognises and checked by hash."""
    if not state(bank)[0]:
        raise OpError("This backup's dongle firmware isn't one the app recognises, so the new firmware can't be made from it. Nothing was written.")
    new = bytearray(bank)
    new[DESC - BASE:DESC - BASE + len(XBOX_DESC)] = XBOX_DESC if xbox else STOCK_DESC
    new = bytes(new)
    if state(new) != (True, xbox):
        raise OpError("The new dongle firmware doesn't match its known checksum. Nothing was written.")
    return new


def _one(find, mode):
    found = [f for f in find() if f.mode == mode]
    return found[0].info if len(found) == 1 else None


def _wait(find, mode, seconds, step):
    end = time.time() + seconds
    while time.time() < end:
        info = _one(find, mode)
        if info:
            return info
        time.sleep(step)
    return None


INTERRUPTED = "The dongle may stay in update mode until it's finished. Use Restore to install your backup or 8BitDo's original firmware 1.03."


def apply(find, open_channel, unit_backup: bytes, bank: bytes, progress, wait: float = 0.3) -> bool:
    """Write bank A as described above; True if the dongle came back on its own afterwards. find and open_channel are
    cli's, so the dongle can be followed as it restarts."""
    assert len(bank) == SIZE and len(unit_backup) == FLASH   # only bank A, never anything else
    boot_info = _one(find, "boot")
    if boot_info is None:
        idle = _one(find, "dongle")
        if idle is None:
            raise OpError("The dongle isn't connected on its own. Turn the controller off and try again. Nothing was written.")
        ch = open_channel(idle, 0x81)
        try:
            if read_unit(ch) != unit_of(unit_backup):
                raise OpError("This dongle doesn't match the backup, so nothing was written.")
            ch.xfer(bytes([0x81, 0x05, 0x00, 0x51, 0x00]).ljust(64, b"\0"), 0.5)
        finally:
            ch.close()
        boot_info = _wait(find, "boot", 8, wait)
        if boot_info is None:
            raise OpError("The dongle didn't restart into update mode, so nothing was written. Unplug it and plug it back in.")
    ch = open_channel(boot_info, 0)
    try:
        try:
            if boot.identify(ch) != boot.DONGLE_ID:
                raise OpError("The device in update mode isn't the dongle, so nothing was written.")
            if boot.read(ch, 0, BOOT_END) != unit_backup[:BOOT_END] or boot.read(ch, CAL, 0x40) != unit_backup[CAL:CAL + 0x40]:
                raise OpError("The dongle in update mode doesn't match the backup, so nothing was written.")
        except protocol.ProtocolError as e:
            raise OpError(f"{e}. Nothing was written.") from e
        try:
            boot.erase(ch, BASE, SIZE)
            done = 0
            for a in range(BASE + CHUNK, END, CHUNK):
                blk = bank[a - BASE:min(a + CHUNK, END) - BASE]
                assert BASE < a and a + len(blk) <= END
                if blk != b"\xff" * len(blk):
                    boot.write_chunk(ch, a, SIZE, blk)
                done += len(blk)
                progress("write", done, SIZE)
            if boot.read(ch, BASE + CHUNK, SIZE - CHUNK) != bank[CHUNK:]:
                raise OpError("The dongle's firmware read back doesn't match what was written. " + INTERRUPTED)
            boot.write_chunk(ch, BASE, SIZE, bank[:CHUNK])
            progress("write", SIZE, SIZE)
            if boot.read(ch, BASE, SIZE) != bank:
                raise OpError("The dongle's firmware read back doesn't match what was written. " + INTERRUPTED)
        except protocol.ProtocolError as e:
            raise OpError(f"{e}. {INTERRUPTED}") from e
        ch.xfer(boot.request(7), 0.5)
    finally:
        ch.close()
    return _wait(find, "dongle", 10, wait) is not None
