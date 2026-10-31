# SPDX-License-Identifier: GPL-3.0-or-later
"""The tweaks, as hash-checked edits to stock v1.09 bank A, and identification of an image.

No 8BitDo bytes live here: an edit's stock content is known only by its SHA-256 (stock_hashes.py), and the rest of
bank A by the hash of stock with every edit region zeroed. Addresses are image addresses (flash = image).
"""
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from . import image
from .image import BASE, BANK_A_SIZE

BLOBS = Path(__file__).parent / "blobs"
NAME = b"8BitDo Ultimate 2C (One)"
OLD_NAME_LEN = 27
PACKER_SLOT = (0xB908, 0xBAD4)


class RecipeError(Exception):
    pass


@dataclass(frozen=True)
class Edit:
    addr: int
    new: bytes
    superseded_by: str | None = None  # recipe whose edit takes over this region when it is present

    @property
    def size(self) -> int:
        return len(self.new)


@dataclass(frozen=True)
class Recipe:
    key: str
    title: str
    requires: tuple[str, ...]
    edits: tuple[Edit, ...]


@dataclass(frozen=True)
class State:
    known: bool
    recipes: tuple[str, ...] = ()


def _blob(name: str) -> bytes:
    return (BLOBS / name).read_bytes()


def _u32(v: int) -> bytes:
    return struct.pack("<I", v)


def _make() -> dict[str, Recipe]:
    pad = bytes(OLD_NAME_LEN - len(NAME))
    slot = PACKER_SLOT[1] - PACKER_SLOT[0]
    return {r.key: r for r in (
        Recipe("bt_xbox", "Bluetooth: Xbox Series X/S controller", (), (
            Edit(PACKER_SLOT[0], _blob("packer.bin").ljust(slot, b"\0")),
            Edit(0x18274, _blob("report-map.bin")),
            Edit(0x18390, _blob("noop.bin"), superseded_by="bt_rumble"),
            Edit(0x177A0, _u32(len(_blob("report-map.bin")))),   # Report Map attribute: length
            Edit(0x177A8, _u32(0x18274)),                        # ... and value pointer
            Edit(0x17764, _u32(0x18391)),                        # output report write callback (Thumb-style odd)
            Edit(0x173C0, bytes.fromhex("025e04130b0905")),      # PnP ID: USB-IF, 045e:0b13, v0509
            Edit(0x18098, bytes.fromhex("0302")),                # output report reference: ID 3, output
            Edit(0x172C0, bytes.fromhex("c403")),                # GAP appearance: gamepad
            Edit(0x172DC, NAME + pad),                           # GATT device name
            Edit(0x17488, _u32(len(NAME))),                      # ... and its length
            Edit(0x17254, bytes([len(NAME) + 1, 9]) + NAME + pad),  # scan response name
            Edit(0xA214, bytes([len(NAME) + 2, 0xA1])),          # scan response length immediate
        )),
        Recipe("bt_rumble", "Bluetooth: rumble", ("bt_xbox",), (
            Edit(0x18390, _blob("rumble.bin")),
        )),
        Recipe("cable_360", "Cable: wired Xbox 360 controller", (), (
            Edit(0x17994, bytes.fromhex("ffffff")),              # class, subclass, protocol
            Edit(0x17998, bytes.fromhex("5e048e02")),            # 045e:028e
        )),
        Recipe("dim_leds", "Dimmer LEDs", (), (
            Edit(0x7738, _blob("led.bin")),                      # main_tick, run from RAM at 0x1738
            Edit(0xA43C, _blob("hook.bin")),                     # main loop calls main_tick instead of 0xfaa0
        )),
    )}


RECIPES: dict[str, Recipe] = _make()


def _constants(stock_sha256, region_sha256, remainder_sha256):
    if stock_sha256 is None or region_sha256 is None or remainder_sha256 is None:
        from . import stock_hashes
        return (stock_sha256 or image.STOCK_SHA256, region_sha256 or stock_hashes.REGION_SHA256,
                remainder_sha256 or stock_hashes.REMAINDER_SHA256)
    return stock_sha256, region_sha256, remainder_sha256


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _region(img: bytes, e: Edit) -> bytes:
    return img[e.addr - BASE:e.addr - BASE + e.size]


def masked(img: bytes) -> bytes:
    """Bank A with every edit region zeroed: what no recipe touches."""
    out = bytearray(img)
    for r in RECIPES.values():
        for e in r.edits:
            out[e.addr - BASE:e.addr - BASE + e.size] = bytes(e.size)
    return bytes(out)


def build(stock: bytes, keys, stock_sha256=None, region_sha256=None, remainder_sha256=None) -> bytes:
    """Stock bank A plus the chosen tweaks. Refuses anything but stock, an unknown tweak or a missing dependency."""
    stock_sha, regions, _ = _constants(stock_sha256, region_sha256, remainder_sha256)
    if len(stock) != BANK_A_SIZE or _sha(stock) != stock_sha:
        raise RecipeError("the base image is not stock v1.09 bank A")
    keys = list(keys)
    for k in keys:
        if k not in RECIPES:
            raise RecipeError(f"unknown tweak {k!r}")
        for need in RECIPES[k].requires:
            if need not in keys:
                raise RecipeError(f"{k} needs {need}")
    img = bytearray(stock)
    for key, r in RECIPES.items():  # recipe order: a dependent's edit lands over the one it supersedes
        if key not in keys:
            continue
        for e in r.edits:
            if _sha(_region(stock, e)) != regions[(e.addr, e.size)]:
                raise RecipeError(f"{key}: stock bytes at {e.addr:#x} are not as expected")
            img[e.addr - BASE:e.addr - BASE + e.size] = e.new
    return bytes(img)


def identify(bank_a: bytes, stock_sha256=None, region_sha256=None, remainder_sha256=None) -> State:
    """Which tweaks a bank A holds, or unknown if any edit region is neither stock nor a tweak's, or the rest differs."""
    _, regions, remainder = _constants(stock_sha256, region_sha256, remainder_sha256)
    if len(bank_a) != BANK_A_SIZE or _sha(masked(bank_a)) != remainder:
        return State(False)

    def edit_state(e):
        got = _region(bank_a, e)
        if got == e.new:
            return "new"
        if _sha(got) == regions[(e.addr, e.size)]:
            return "stock"
        # the region a tweak takes over from another's (noop callback -> rumble) reads as untouched while the other is present
        if any(o.addr == e.addr and o.superseded_by and e in RECIPES[o.superseded_by].edits and got == o.new.ljust(e.size, b"\0")
               for r in RECIPES.values() for o in r.edits):
            return "stock"
        return "other"

    plain = {k: [edit_state(e) for e in r.edits if e.superseded_by is None] for k, r in RECIPES.items()}
    present = {k for k, s in plain.items() if s and all(x == "new" for x in s)}
    for k, r in RECIPES.items():
        s = plain[k] + [edit_state(e) for e in r.edits if e.superseded_by is not None and e.superseded_by not in present]
        if "other" in s or ("new" in s and "stock" in s):
            return State(False)
    present = {k for k in RECIPES if all(
        edit_state(e) == "new" for e in RECIPES[k].edits if e.superseded_by not in present)}
    for k in present:
        if any(need not in present for need in RECIPES[k].requires):
            return State(False)
    return State(True, tuple(sorted(present)))
