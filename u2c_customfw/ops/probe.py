# SPDX-License-Identifier: GPL-3.0-or-later
"""Read bank A of the connected controller (read-only) and say which firmware it holds."""
from .. import protocol
from ..firmware import image, recipes
from ..protocol import app, boot
from .plan import OpError


def read_state(ch, mode: str) -> recipes.State:
    """Stock v1.09 plus which tweaks, or unknown. By cable (update channel) or in boot mode."""
    try:
        if mode == "boot":
            if boot.kind(ch) != "controller":
                raise OpError("the device in boot mode is not a controller (the dongle is not supported)")
            bank_a = boot.read(ch, image.BASE, image.BANK_A_SIZE)
        else:
            if app.open_session(ch) is None:
                raise OpError("the controller does not answer reads: unplug it, plug it back in and try again")
            if app.read(ch, 0x10000, 16) == b"\xff" * 16:
                raise OpError("this looks like the 2.4 GHz dongle, which this app does not support")
            out = bytearray()
            for a in range(image.BASE, image.BANK_A_END, boot.CHUNK):
                c = app.read(ch, a, min(boot.CHUNK, image.BANK_A_END - a))
                if c is None:
                    raise OpError(f"the controller did not answer at {a:#x}")
                out += c
            bank_a = bytes(out)
    except protocol.ProtocolError as e:
        raise OpError(str(e)) from e
    return recipes.identify(bank_a)
