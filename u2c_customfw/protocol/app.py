# SPDX-License-Identifier: GPL-3.0-or-later
"""Normal-mode reads through the running controller's update channel (output report 0x81, input report 0x02).

Reads are `81 05 05` (any address, at most 46 bytes). The only other commands sent are the Home ring's two, which
only the ring tweak acts on, with no reply: `81 05 00 52 <level>` and `81 05 00 53` (see docs/firmware-notes.md). Reads are tried
first; if they get no answer, the session start `81 05 00 21 01` (it only replies) is sent, and if reads still fail,
`81 05 c1`, which turns the flash's write protection off until the controller restarts and changes no data.
`81 05 00 51 00` restarts the controller into update mode, only to install or restore by cable (enter_update_mode).
"""
import time

SESSION_START = bytes([0x81, 0x05, 0x00, 0x21, 0x01]).ljust(64, b"\0")
WRITE_UNPROTECT = bytes([0x81, 0x05, 0xC1]).ljust(64, b"\0")


def _req(addr: int, n: int) -> bytes:
    r = bytearray(64)
    r[0:3] = b"\x81\x05\x05"
    r[6:8] = n.to_bytes(2, "little")
    r[14:18] = addr.to_bytes(4, "little")
    return bytes(r)


def read(ch, addr: int, n: int, tries: int = 3) -> bytes | None:
    """One chunk, accepted only if the reply echoes status 0, the read command, the length and the address."""
    def answers(r):
        return (len(r) >= 18 + n and r[0:3] == b"\x02\x05\x00" and r[4] == 0x05
                and int.from_bytes(r[6:8], "little") == n and int.from_bytes(r[14:18], "little") == addr)
    for _ in range(tries):
        r = ch.xfer(_req(addr, n), accept=answers)
        if r and answers(r):
            return r[18:18 + n]
    return None


def enter_update_mode(ch) -> None:
    """Restarts the controller into update mode: the firmware sets analog register 0x3c to 0x5a, which the bootloader checks
    at start-up, so it stays there until the bootloader's restart command (7) or until the power is cut. No reply."""
    _command(ch, 0x51, 0x00)


def set_ring(ch, level: int) -> None:
    """The Home ring tweak's live level, 0-5. It changes RAM only, and there is no reply."""
    ch.xfer(bytes([0x81, 0x05, 0x00, 0x52, level]).ljust(64, b"\0"), 0.3)


def save_ring(ch) -> None:
    """Asks the Home ring tweak to keep its level: the firmware saves it, in its own settings record."""
    ch.xfer(bytes([0x81, 0x05, 0x00, 0x53]).ljust(64, b"\0"), 0.3)


def _command(ch, *data: int) -> None:
    """A command with no reply, so nothing to wait for once it has gone out."""
    ch.xfer(bytes([0x81, 0x05, 0x00, *data]).ljust(64, b"\0"), 0.02)


def set_field(ch, number: int, value: int) -> None:
    """A controller setting, in RAM, where it applies at once."""
    _command(ch, 0x54, number, value)


def settings_save(ch) -> None:
    """Asks the firmware to keep the settings. It does so on its next 100 ms pass."""
    _command(ch, 0x55)


def settings_reset(ch) -> None:
    """Asks the firmware to go back to its defaults, and keep them."""
    _command(ch, 0x56)


def settings_reload(ch) -> None:
    """Asks the firmware to drop unsaved settings and read its record again, on its next 100 ms pass."""
    _command(ch, 0x5A)


def set_mapping(ch, slot: int, mask: int) -> None:
    """What L4 (slot 1) or R4 (slot 0) presses, as button word bits."""
    _command(ch, 0x57, slot, *mask.to_bytes(4, "little"))


def set_dead_zone(ch, off: bool) -> None:
    """The firmware's own dead zone switch, the one Start + Select changes."""
    _command(ch, 0x58, 1 if off else 0)


def open_session(ch) -> str | None:
    """Make reads work. Returns 'cold', 'session' or 'unprotect' (what had to be sent), or None."""
    if read(ch, 0x10000, 16, tries=2) is not None:
        return "cold"
    for _ in range(4):
        ch.xfer(SESSION_START, 0.8)
        time.sleep(0.02)
        if read(ch, 0x10000, 16, tries=2) is not None:
            return "session"
    ch.xfer(WRITE_UNPROTECT, 0.8)
    time.sleep(0.02)
    if read(ch, 0x10000, 16, tries=3) is not None:
        return "unprotect"
    return None
