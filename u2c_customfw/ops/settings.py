# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller settings, through an open channel to the running controller, by cable. The app only asks: the firmware
does the writing, to its own records."""
import time

from .. import settings
from ..firmware import image, recipes
from ..protocol import app
from .plan import OpError

CONFIRM_SECONDS = 1.0
PASS = 0.15   # the firmware acts on settings commands every 100 ms
NO_ANSWER = "The controller didn't answer. Check the cable and try again."
_R4, _L4 = 1 << 25, 1 << 26  # what stock's records hold for "not mapped", or 0, or all ones
_HOOK = next(e.new for e in recipes.RECIPES["settings"].edits if e.addr == settings.INSTALLED_HOOK)


def _read(ch, addr: int, n: int) -> bytes:
    data = app.read(ch, addr, n)
    if data is None:
        raise OpError(NO_ANSWER)
    return data


def installed(ch) -> bool:
    return _read(ch, settings.INSTALLED_HOOK, 4) == _HOOK


def _mapping(raw: bytes, own: int) -> int:
    mask = int.from_bytes(raw, "little")
    return 0 if mask in (0, 0xFFFFFFFF, own) else mask & settings.MAP_MASK


def read(ch) -> dict:
    """What the controller has kept."""
    values = settings.parse(_read(ch, settings.SECTOR, settings.SIZE))
    stock = _read(ch, image.SETTINGS, image.SETTINGS_SIZE)
    return {"values": values or dict(settings.DEFAULTS), "saved": values is not None, "dead_zone_off": stock[6] == 1,
            "mapping": {"r4": _mapping(stock[17:21], _R4), "l4": _mapping(stock[21:25], _L4)}}


def load(ch) -> dict:
    """What it has kept, with its RAM brought back to that, because changes it hasn't saved can't be read: what the page shows
    is then what the controller is doing. Unsaved changes are dropped."""
    kept = read(ch)
    app.settings_reload(ch)
    time.sleep(PASS)   # the firmware ignores commands until its next pass has read the record again
    app.set_dead_zone(ch, kept["dead_zone_off"])
    app.set_mapping(ch, 0, kept["mapping"]["r4"])
    app.set_mapping(ch, 1, kept["mapping"]["l4"])
    return kept


def _kept(ch, values: dict, mapping=None, dead_zone_off=None) -> bool:
    """The firmware saves on its next 100 ms pass, which a record that already matches can't show, so this waits for it first."""
    time.sleep(PASS)
    end = time.monotonic() + CONFIRM_SECONDS
    while True:
        got = read(ch)
        if got["saved"] and got["values"] == values and mapping in (None, got["mapping"]) and dead_zone_off in (None, got["dead_zone_off"]):
            return True
        if time.monotonic() > end:
            return False
        time.sleep(0.05)


def change(ch, values: dict) -> None:
    for name, value in values.items():
        app.set_field(ch, settings.BY_NAME[name].number, value)


def save(ch, values: dict, mapping=None, dead_zone_off=None) -> bool:
    """Asks the firmware to save, then checks what it wrote."""
    app.settings_save(ch)
    return _kept(ch, values, mapping, dead_zone_off)


def still_there(ch) -> None:
    """Commands get no reply, so a failed one looks like any other: this notices a controller that has gone."""
    _read(ch, settings.INSTALLED_HOOK, 4)


def reset(ch) -> dict:
    app.settings_reset(ch)
    if not _kept(ch, settings.DEFAULTS, {"r4": 0, "l4": 0}, False):
        raise OpError("The controller didn't confirm the reset. Check the cable and try again.")
    return dict(settings.DEFAULTS)
