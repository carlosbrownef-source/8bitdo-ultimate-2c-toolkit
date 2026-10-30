# SPDX-License-Identifier: GPL-3.0-or-later
"""Bootloader protocol (2dc8:3208), as reversed by jgus from 8BitDo's updater.

64-byte reports, no report ID: [0]=05 [1:3]=cmd [5:7]=data length [7:9]=CRC-16/MODBUS of the data [9:13]=param
[13:17]=address [17:]=data. cmd 5 read (param = length, data at reply[18]), 4 erase (param = length, 4 KB units),
3 write (<= 46 bytes). Reply [0]=0 [1]=5 [2]=0 [4]=cmd is success.
"""
from . import ProtocolError

CHUNK = 46


def crc16(data: bytes) -> int:
    c = 0xFFFF
    for x in data:
        c ^= x
        for _ in range(8):
            c = c >> 1 ^ 0xA001 if c & 1 else c >> 1
    return c


def request(cmd: int, addr: int = 0, param: int = 0, data: bytes = b"", datalen: int | None = None) -> bytes:
    r = bytearray(64)
    r[0] = 0x05
    r[1:3] = cmd.to_bytes(2, "little")
    r[5:7] = (len(data) if datalen is None else datalen).to_bytes(2, "little")
    r[7:9] = crc16(data).to_bytes(2, "little") if data else b"\0\0"
    r[9:13] = param.to_bytes(4, "little")
    r[13:17] = addr.to_bytes(4, "little")
    r[17:17 + len(data)] = data
    return bytes(r)


def _call(ch, r: bytes, timeout=1.0, tries=3):
    for _ in range(tries):
        a = ch.xfer(r, timeout)
        if a and len(a) >= 5 and a[0] == 0 and a[1] == 5 and a[2] == 0 and a[4] == r[1]:
            return a
    return None


def read(ch, addr: int, n: int, progress=None) -> bytes:
    out = bytearray()
    while len(out) < n:
        k = min(CHUNK, n - len(out))
        a = _call(ch, request(5, addr + len(out), k, datalen=k))
        if a is None:
            raise ProtocolError(f"no valid reply reading {addr + len(out):#x}")
        out += a[18:18 + k]
        if progress:
            progress(len(out), n)
    return bytes(out)


def erase(ch, addr: int, n: int) -> None:
    if _call(ch, request(4, addr, n), timeout=10.0, tries=1) is None:
        raise ProtocolError(f"erase of {addr:#x}-{addr + n:#x} failed")


def write_chunk(ch, addr: int, param: int, data: bytes) -> None:
    if _call(ch, request(3, addr, param, data)) is None:
        raise ProtocolError(f"write at {addr:#x} rejected")


def kind(ch) -> str | None:
    """The dongle's 128 KB flash reads back aliased above 0x20000; the controller's 0x20000 is erased."""
    lo, hi = read(ch, 0, 16), read(ch, 0x20000, 16)
    if hi == b"\xff" * 16:
        return "controller"
    if hi == lo and lo != b"\xff" * 16:
        return "dongle"
    return None
