# SPDX-License-Identifier: GPL-3.0-or-later
"""Find the controller (or dongle) in whatever mode it is in."""
from dataclasses import dataclass

from .. import transport
from ..transport import DeviceInfo

# (vendor, product, usage page or None) -> mode. The update channel of the running controller is vendor page 0xff7a.
MODES = (
    (0x2DC8, 0x310A, 0xFF7A, "cable"),
    (0x045E, 0x028E, 0xFF7A, "cable_360"),
    (0x2DC8, 0x3208, None, "boot"),
    (0x2DC8, 0x301C, 0xFFA0, "dongle"),
    (0x045E, 0x0B13, None, "bluetooth_xbox"),
    (0x2DC8, 0x301B, None, "bluetooth"),
)


@dataclass
class Found:
    info: DeviceInfo
    mode: str


def find() -> list[Found]:
    """Every controller-like device found (two units are two entries); a Bluetooth pad shows several HID interfaces
    and is listed once. Other HID devices are ignored."""
    out: list[Found] = []
    for d in transport.list_devices():
        for vendor, product, page, mode in MODES:
            if d.vendor == vendor and d.product == product and (page is None or d.usage_page == page):
                if mode.startswith("bluetooth"):
                    if "Bluetooth" not in d.transport or any(f.mode == mode for f in out):
                        continue
                out.append(Found(d, mode))
    return out
