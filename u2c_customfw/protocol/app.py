# SPDX-License-Identifier: GPL-3.0-or-later
"""Normal-mode reads through the running controller's update channel (output report 0x81, input report 0x02).

Reads are `81 05 05` (any address, at most 46 bytes). The only other commands sent are the Home ring's two, which
only the ring tweak answers: `81 05 00 52 <level>` and `81 05 00 53` (see docs/firmware-notes.md). Reads are tried
first; if they get no answer, the session start `81 05 00 21 01` (it only replies) is sent, and if reads still fail,
`81 05 c1`, which turns the flash's write protection off until the controller restarts and changes no data.
`81 05 00 51` (reboot into the bootloader) is never sent.
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
    for _ in range(tries):
        r = ch.xfer(_req(addr, n))
        if (r and len(r) >= 18 + n and r[0:3] == b"\x02\x05\x00" and r[4] == 0x05
                and int.from_bytes(r[6:8], "little") == n and int.from_bytes(r[14:18], "little") == addr):
            return r[18:18 + n]
    return None


def set_ring(ch, level: int) -> None:
    """The Home ring tweak's live level, 0-5. It changes RAM only, and there is no reply."""
    ch.xfer(bytes([0x81, 0x05, 0x00, 0x52, level]).ljust(64, b"\0"), 0.3)


def save_ring(ch) -> None:
    """Asks the Home ring tweak to keep its level: the firmware saves it, in its own settings record."""
    ch.xfer(bytes([0x81, 0x05, 0x00, 0x53]).ljust(64, b"\0"), 0.3)


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
