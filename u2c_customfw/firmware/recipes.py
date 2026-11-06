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
NAME = b"8BitDo Ultimate 2C (X/S)"
OLD_NAME = b"8BitDo Ultimate 2C (One)"  # what versions before 0.2 installed: still recognised, never written
OLD_NAME_LEN = 27
PACKER_SLOT = (0xB908, 0xBAD4)
RING_LEVELS = (("ring_off", "Home ring: off", 0), ("ring_0_1", "Home ring: 0.1 %", 1), ("ring_1", "Home ring: 1 %", 10),
               ("ring_5", "Home ring: 5 %", 50), ("ring_25", "Home ring: 25 %", 250),
               ("ring_normal", "Home ring: normal", 0xFFFF))  # PWM1 compare value, period 1000; normal doesn't use it
OLD_RING_LEVELS = RING_LEVELS[:5]                             # what 0.2.0 could install
RING_ORDER = ("ring_normal", "ring_25", "ring_5", "ring_1", "ring_0_1", "ring_off")  # the firmware's level numbers
RING_CODE = (0x18400, 0x18FF0)                                # blank on stock
ALERTS_FLAG = 0x18FF0
SETTINGS_FLAG = 0x18FF1
STICK_THRESHOLD = 8                                           # stock's is 20; not measured yet on a real controller


class RecipeError(Exception):
    pass


@dataclass(frozen=True)
class Edit:
    addr: int
    new: bytes
    superseded_by: str | None = None  # recipe whose edit takes over this region when it is present
    accepts: tuple[bytes, ...] = ()   # earlier contents of this edit that still count as installed

    @property
    def size(self) -> int:
        return len(self.new)


@dataclass(frozen=True)
class Recipe:
    key: str
    title: str
    requires: tuple[str, ...]
    edits: tuple[Edit, ...]
    group: str | None = None  # at most one recipe of a group can be installed
    requires_group: str | None = None  # one recipe of this group must be installed too
    earlier_form_of: str | None = None  # how an earlier version installed that recipe: recognised, not installable


@dataclass(frozen=True)
class State:
    known: bool
    recipes: tuple[str, ...] = ()
    outdated: bool = False  # has a tweak in the form an earlier version installed it


def _blob(name: str) -> bytes:
    return (BLOBS / name).read_bytes()


def _u32(v: int) -> bytes:
    return struct.pack("<I", v)


def _make() -> dict[str, Recipe]:
    pad = bytes(OLD_NAME_LEN - len(NAME))
    slot = PACKER_SLOT[1] - PACKER_SLOT[0]
    return {r.key: r for r in (
        Recipe("bt_xbox", "Xbox Series X|S controller over Bluetooth", (), (
            Edit(PACKER_SLOT[0], _blob("packer.bin").ljust(slot, b"\0")),
            Edit(0x18274, _blob("report-map.bin")),
            Edit(0x18390, _blob("noop.bin"), superseded_by="bt_rumble"),
            Edit(0x177A0, _u32(len(_blob("report-map.bin")))),   # Report Map attribute: length
            Edit(0x177A8, _u32(0x18274)),                        # ... and value pointer
            Edit(0x17764, _u32(0x18391)),                        # output report write callback (Thumb-style odd)
            Edit(0x173C0, bytes.fromhex("025e04130b0905")),      # PnP ID: USB-IF, 045e:0b13, v0509
            Edit(0x18098, bytes.fromhex("0302")),                # output report reference: ID 3, output
            Edit(0x172C0, bytes.fromhex("c403")),                # GAP appearance: gamepad
            Edit(0x172DC, NAME + pad, accepts=(OLD_NAME + pad,)),  # GATT device name
            Edit(0x17488, _u32(len(NAME))),                      # ... and its length
            Edit(0x17254, bytes([len(NAME) + 1, 9]) + NAME + pad,
                 accepts=(bytes([len(OLD_NAME) + 1, 9]) + OLD_NAME + pad,)),  # scan response name
            Edit(0xA214, bytes([len(NAME) + 2, 0xA1])),          # scan response length immediate
        )),
        Recipe("bt_rumble", "Rumble over Bluetooth", ("bt_xbox",), (
            Edit(0x18390, _blob("rumble.bin").ljust(0x70, b"\0"),
                 accepts=(_blob("rumble02.bin").ljust(0x70, b"\0"), _blob("rumble03.bin").ljust(0x70, b"\0"))),
        )),
        Recipe("cable_360", "Xbox 360 controller over cable", (), (
            Edit(0x17994, bytes.fromhex("ffffff")),              # class, subclass, protocol
            Edit(0x17998, bytes.fromhex("5e048e02")),            # 045e:028e
        )),
        Recipe("dim_leds", "Dimmer LEDs", (), (
            Edit(0x7738, _blob("led.bin")),                      # main_tick, run from RAM at 0x1738
            Edit(0xA43C, _blob("hook.bin")),                     # main loop calls main_tick instead of 0xfaa0
        )),
        *(Recipe(key + at, title, (), (
            Edit(0xA3FA, b"\0"),                                 # the ring doesn't light up at startup
            Edit(0xD4F0, _blob(f"ringhook{form}.bin")),          # LED task calls ring_tick for the ring
            Edit(0xF83C, _blob(f"vhooka{form}.bin")),            # vendor commands reach ring_vendor
            Edit(0xF842, _blob(f"vhookb{form}.bin")),
            Edit(0xA484, _blob(f"pollhook{form}.bin")),          # main loop samples the L4 + R4 chord
            Edit(0x7640, bytes(0x90)),                           # dead RAM code, now the ring's and settings' state
            Edit(0x76D0, level.to_bytes(2, "little")),           # the level installed
            Edit(RING_CODE[0], _blob(f"ringtail{form}.bin").ljust(RING_CODE[1] - RING_CODE[0], b"\xff")),
        ), "ring", earlier_form_of=key if form else None)
            for form, at in (("", ""), ("03", "@0.3")) for key, title, level in RING_LEVELS),
        *(Recipe(f"{key}@0.2", title, (), (
            Edit(0xA3FA, b"\0"),
            Edit(0xD4F0, _blob("ringhook02.bin")),
            Edit(0x7640, _blob("ring02.bin").ljust(0x90, b"\0")),
            Edit(0x76D0, level.to_bytes(2, "little")),
        ), "ring", earlier_form_of=key) for key, title, level in OLD_RING_LEVELS),
        Recipe("battery_alerts", "Battery alerts", (), (
            Edit(ALERTS_FLAG, b"\1"),
        ), requires_group="ring"),
        Recipe("settings", "Controller settings", (), (
            Edit(0xDCE6, _blob("hgamea.bin")),                   # the games' rumble over 2.4 GHz ...
            Edit(0xEAF4, _blob("hgameb.bin")),                   # ... and by cable, at the chosen intensity
            Edit(0xA0F8, _blob("hbuzza.bin")),                   # vibrating on connecting, Bluetooth ...
            Edit(0xDAA8, _blob("hbuzzb.bin")),                   # ... and 2.4 GHz
            Edit(0xD1C8, _blob("hidle.bin")),                    # the idle limit, from the settings
            Edit(0x6A90, _blob("hstickl.bin")),                  # each stick's dead zone code, run from RAM at 0xa90 ...
            Edit(0x6ABC, _blob("hstickr.bin")),                  # ... and 0xabc
            Edit(0xC910, _blob("hscan.bin")),                    # the button scan: triggers and remapping
            Edit(0x7210, _blob("sram.bin").ljust(0xC0, b"\0")),   # scan_hook, run from RAM at 0x1210 (dead RAM code)
            Edit(SETTINGS_FLAG, b"\1"),                          # the code is there with any Home ring level: this says it's in use
        ), requires_group="ring"),
        Recipe("fixes", "Fixes", (), (
            Edit(0xA480, _blob("hidletask.bin")),                # sticks count as activity; a lost connection searches for its full time
            Edit(0xEA88, _blob("hunplug.bin")),                  # unplugging in the Bluetooth position restarts, to find the Mac at once
            Edit(0x178CC, _blob("hota.bin")),                    # the unencrypted Bluetooth firmware update's write handler
        ), requires_group="ring"),
        Recipe("stick_precision", "Finer stick movement", (), (
            *(Edit(a, bytes([STICK_THRESHOLD])) for a in (0xB1F2, 0xB208, 0xB220, 0xB238)),  # the jitter filter's threshold
            Edit(0xA2DC, _blob("hsweep.bin")),                   # two ADC passes per report, so its average means something
        ), requires_group="ring"),
        Recipe("ble_interval", "Standard Bluetooth connection request", (), (
            Edit(0xA0DE, bytes.fromhex("09a00ca100a2c8a3")),     # min 11.25 ms, max 15 ms, latency 0, timeout 2 s, instead of 7.5 ms and latency 59
        )),
        Recipe("soft_rumble", "Softer rumble start", (), (
            Edit(0xF968, bytes.fromhex("01aa")),                 # the 95 % start lasts 2 ticks rather than 4
        )),
    )}


RECIPES: dict[str, Recipe] = _make()


def _constants(stock_sha256, region_sha256, remainder_sha256):
    if stock_sha256 is None or region_sha256 is None or remainder_sha256 is None:
        from . import stock_hashes
        return (stock_sha256 or image.STOCK_SHA256, region_sha256 or stock_hashes.REGION_SHA256,
                remainder_sha256 or stock_hashes.REMAINDER_SHA256)
    return stock_sha256, region_sha256, remainder_sha256


def whole(img: bytes) -> bytes:
    """The whole app area: a v1.09 payload gets its blank tail."""
    return img + b"\xff" * (image.APP_SIZE - BANK_A_SIZE) if len(img) == BANK_A_SIZE else img


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _region(img: bytes, e: Edit) -> bytes:
    return img[e.addr - BASE:e.addr - BASE + e.size]


def masked(img: bytes) -> bytes:
    """The app area with every edit region zeroed: what no recipe touches."""
    out = bytearray(img)
    for r in RECIPES.values():
        for e in r.edits:
            out[e.addr - BASE:e.addr - BASE + e.size] = bytes(e.size)
    return bytes(out)


def build(stock: bytes, keys, stock_sha256=None, region_sha256=None, remainder_sha256=None) -> bytes:
    """The app area: stock plus the chosen tweaks. Refuses anything but stock, an unknown tweak or a missing dependency."""
    stock_sha, regions, _ = _constants(stock_sha256, region_sha256, remainder_sha256)
    if len(stock) != BANK_A_SIZE or _sha(stock) != stock_sha:
        raise RecipeError("the base image is not stock v1.09 bank A")
    keys = list(keys)
    for k in keys:
        if k not in RECIPES or RECIPES[k].earlier_form_of:
            raise RecipeError(f"unknown tweak {k!r}")
        for need in RECIPES[k].requires:
            if need not in keys:
                raise RecipeError(f"{k} needs {need}")
        if RECIPES[k].requires_group and not any(RECIPES[o].group == RECIPES[k].requires_group for o in keys):
            raise RecipeError(f"{k} needs a Home ring level")
    groups = [RECIPES[k].group for k in keys if RECIPES[k].group]
    if len(groups) != len(set(groups)):
        raise RecipeError("choose only one Home ring level")
    base = whole(stock)
    img = bytearray(base)
    for key, r in RECIPES.items():  # recipe order: a dependent's edit lands over the one it supersedes
        if key not in keys:
            continue
        for e in r.edits:
            if _sha(_region(base, e)) != regions[(e.addr, e.size)]:
                raise RecipeError(f"{key}: stock bytes at {e.addr:#x} are not as expected")
            img[e.addr - BASE:e.addr - BASE + e.size] = e.new
    return bytes(img)


def identify(bank_a: bytes, stock_sha256=None, region_sha256=None, remainder_sha256=None) -> State:
    """Which tweaks an app area holds, or unknown if any edit region is neither stock nor a tweak's, or the rest differs.
    A bare payload counts as having a blank tail."""
    _, regions, remainder = _constants(stock_sha256, region_sha256, remainder_sha256)
    bank_a = whole(bank_a)
    if len(bank_a) != image.APP_SIZE or _sha(masked(bank_a)) != remainder:
        return State(False)

    def edit_state(e):
        got = _region(bank_a, e)
        if got == e.new or got in e.accepts:
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
    chosen = {RECIPES[k].group for k in present} - {None}
    for k, r in RECIPES.items():
        if r.group in chosen and k not in present:  # the group's other options share regions with the installed one
            continue
        s = plain[k] + [edit_state(e) for e in r.edits if e.superseded_by is not None and e.superseded_by not in present]
        if "other" in s or ("new" in s and "stock" in s):
            return State(False)
    present = {k for k in RECIPES if all(
        edit_state(e) == "new" for e in RECIPES[k].edits if e.superseded_by not in present)}
    for k in present:
        if any(need not in present for need in RECIPES[k].requires):
            return State(False)
        if RECIPES[k].requires_group and not any(RECIPES[o].group == RECIPES[k].requires_group for o in present):
            return State(False)
    names = {RECIPES[k].earlier_form_of or k for k in present}
    return State(True, tuple(sorted(names)), any(RECIPES[k].earlier_form_of for k in present))
