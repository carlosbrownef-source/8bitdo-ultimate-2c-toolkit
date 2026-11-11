# SPDX-License-Identifier: GPL-3.0-or-later
"""Device access: the only OS-specific part. A port adds a module with list_devices() and open_channel()."""
import sys
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DeviceInfo:
    vendor: int
    product: int
    usage_page: int
    transport: str
    name: str
    handle: object
    version: int = 0   # bcdDevice


class Channel(Protocol):
    def xfer(self, report: bytes, timeout: float = 0.5, accept=None) -> bytes | None: ...

    def close(self) -> None: ...


class PermissionDenied(Exception):
    """The OS refused to open the device (macOS: Input Monitoring not granted)."""


def _backend():
    if sys.platform == "darwin":
        from . import iokit
        return iokit
    raise NotImplementedError(f"no transport for {sys.platform}: see docs/porting.md")


def list_devices() -> list[DeviceInfo]:
    return _backend().list_devices()


def open_channel(dev: DeviceInfo, report_id: int) -> Channel:
    """report_id 0x81 for the controller's update channel, 0 for the bootloader (no report IDs)."""
    return _backend().open_channel(dev, report_id)
