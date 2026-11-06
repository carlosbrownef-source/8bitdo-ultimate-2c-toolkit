# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller settings record at flash 0x7a000, which only the firmware writes: firmware-src/settings.c and settings.h.

Bytes 0-3 "U2CS", 4 the version, 5-32 the fields below in order, 33-34 the CRC. A field's number on the wire is its place
in FIELDS. Anything the firmware would refuse parses as None, and the firmware then runs on its defaults.
"""
from dataclasses import dataclass

SECTOR = 0x7A000
SIZE = 35
VERSION = 1
MAGIC = b"U2CS"
BUTTONS = 14  # word bits 0-13: the buttons that can be remapped
NOTHING = 0xFF  # a remapped button that does nothing
INSTALLED_HOOK = 0xD1C8  # the settings tweak's idle hook: this is how the app knows it's there, quickly
MAP_MASK = 0xFFFF  # what L4 or R4 can press: word bits 0-15, the triggers among them


@dataclass(frozen=True)
class Field:
    name: str
    number: int
    low: int
    high: int
    default: int
    choices: tuple[int, ...] | None = None


_SHAPE = (("dz_l", 0, 30, 14), ("dz_r", 0, 30, 14), ("outer_l", 70, 100, 100), ("outer_r", 70, 100, 100), ("curve_l", 0, 2, 0),
          ("curve_r", 0, 2, 0), ("invert", 0, 15, 0), ("lt_start", 0, 40, 0), ("lt_end", 60, 100, 100), ("rt_start", 0, 40, 0),
          ("rt_end", 60, 100, 100))
_TIMES = (0, 25, 50, 75, 100), (5, 10, 15, 30, 60)
FIELDS: tuple[Field, ...] = (
    *(Field(n, i, lo, hi, d) for i, (n, lo, hi, d) in enumerate(_SHAPE)),
    Field("vibration", 11, 0, 100, 100, _TIMES[0]),
    Field("idle_min", 12, 5, 60, 15, _TIMES[1]),
    Field("buzz", 13, 0, 1, 1),
    *(Field(f"remap_{i}", 14 + i, 0, NOTHING, i, (*range(BUTTONS), NOTHING)) for i in range(BUTTONS)),
)
BY_NAME = {f.name: f for f in FIELDS}
DEFAULTS = {f.name: f.default for f in FIELDS}


def valid(name, value) -> bool:
    f = BY_NAME.get(name)
    if f is None or type(value) is not int:
        return False
    return value in f.choices if f.choices else f.low <= value <= f.high


def crc(data: bytes) -> int:
    """As the firmware's 0xaf80."""
    c = 0xFFFF
    for b in data:
        c ^= b
        for _ in range(8):
            c = c >> 1 ^ 0x8408 if c & 1 else c >> 1
    return (c >> 8 | c << 8) & 0xFFFF


def parse(raw: bytes) -> dict | None:
    if len(raw) != SIZE or raw[:4] != MAGIC or raw[4] != VERSION:
        return None
    if int.from_bytes(raw[33:35], "little") != crc(raw[:33]):
        return None
    values = {f.name: raw[5 + f.number] for f in FIELDS}
    return values if all(valid(n, v) for n, v in values.items()) else None


def encode(values: dict) -> bytes:
    body = MAGIC + bytes([VERSION]) + bytes(values[f.name] for f in FIELDS)
    return body + crc(body).to_bytes(2, "little")
