# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller settings, through an open channel to the running controller, by cable. The app only asks: the firmware
does the writing, to its own records."""
import time

from .. import settings
from ..firmware import image, recipes
from ..protocol import app
from .plan import OpError

CONFIRM_SECONDS = 1.0
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
    """What the controller has kept. Changes it hasn't saved are in its RAM, where they can't be read."""
    values = settings.parse(_read(ch, settings.SECTOR, settings.SIZE))
    stock = _read(ch, image.SETTINGS, image.SETTINGS_SIZE)
    return {"values": values or dict(settings.DEFAULTS), "saved": values is not None, "dead_zone_off": stock[6] == 1,
            "mapping": {"r4": _mapping(stock[17:21], _R4), "l4": _mapping(stock[21:25], _L4)}}


def _kept(ch, values: dict) -> bool:
    """The firmware saves on its next 100 ms pass."""
    end = time.monotonic() + CONFIRM_SECONDS
    while True:
        if settings.parse(_read(ch, settings.SECTOR, settings.SIZE)) == values:
            return True
        if time.monotonic() > end:
            return False
        time.sleep(0.05)


def change(ch, values: dict) -> None:
    for name, value in values.items():
        app.set_field(ch, settings.BY_NAME[name].number, value)


def save(ch, values: dict) -> bool:
    """Asks the firmware to save, then checks what it wrote."""
    app.settings_save(ch)
    return _kept(ch, values)


def reset(ch) -> dict:
    app.settings_reset(ch)
    if not _kept(ch, settings.DEFAULTS):
        raise OpError("The controller didn't confirm the reset. Check the cable and try again.")
    return dict(settings.DEFAULTS)
