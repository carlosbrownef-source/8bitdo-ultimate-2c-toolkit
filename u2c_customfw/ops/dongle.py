# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the idle 2.4 GHz dongle (2dc8:301c) without changing it: which firmware it holds, and whether it presents as a
wired Xbox 360 pad. The same `81 05 05` reads as the controller's (protocol/app.py); nothing else is sent."""
import hashlib
from dataclasses import dataclass

from ..protocol import app
from .plan import OpError
from .probe import parse_version

BASE, SIZE = 0x6000, 0xA000   # bank A: the whole application
RECORD = 0x12000              # the update record; the version times 100 at +0x0c
STOCK_SHA256 = "15caaa7c705629c768dc7c22417abf047cb06b499376c5c8b8fe14c0f606028c"     # 8BitDo's v1.03
XBOX360_SHA256 = "3c09da195ae59a7dee63c54621b64afca5fa5dfe131989d655f1acb284c6cbd5"   # v1.03 presenting as a wired Xbox 360 pad, bcdDevice 0x0103
CHUNK = 46                    # the largest read the dongle answers


@dataclass
class DongleFirmware:
    known: bool
    version: float | None
    xbox360: bool


def _read(ch, addr: int, n: int) -> bytes:
    out = bytearray()
    for a in range(addr, addr + n, CHUNK):
        c = app.read(ch, a, min(CHUNK, addr + n - a))
        if c is None:
            raise OpError(f"The dongle didn't answer at {a:#x}. Unplug it, plug it back in and try again.")
        out += c
    return bytes(out)


def read_firmware(ch, stock_sha256: str | None = None, xbox360_sha256: str | None = None) -> DongleFirmware:
    """v1.03 as 8BitDo ships it or with the Xbox 360 change, by hash; otherwise the version its update record gives."""
    stock_sha256, xbox360_sha256 = stock_sha256 or STOCK_SHA256, xbox360_sha256 or XBOX360_SHA256
    h = hashlib.sha256(_read(ch, BASE, SIZE)).hexdigest()
    if h in (stock_sha256, xbox360_sha256):
        return DongleFirmware(True, 1.03, h == xbox360_sha256)
    return DongleFirmware(False, parse_version(_read(ch, RECORD, 16)), False)
