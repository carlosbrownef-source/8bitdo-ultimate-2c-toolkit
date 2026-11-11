# SPDX-License-Identifier: GPL-3.0-or-later
"""Patch: stock v1.09 bank A plus tweaks, written through the bootloader."""
from .. import protocol
from ..firmware import image, recipes
from ..protocol import boot
from . import probe, shown
from .plan import OpError, Plan, apply, count, listed  # noqa: F401  (apply is part of this module's interface)


def check_unit(ch, backup, mode: str = "boot") -> None:
    """The controller, in update mode or by cable, must have this backup's bootloader and address. By cable, the caller has
    already checked that it isn't the dongle."""
    if len(backup.data) != image.FLASH_SIZE:
        raise OpError("This isn't a full backup of the controller.")
    try:
        if mode == "boot" and boot.kind(ch) != "controller":
            raise OpError("The device in update mode isn't a controller. The 2.4 GHz dongle isn't supported.")
        if probe._read(ch, mode, 0, image.BOOT_END) != backup.data[:image.BOOT_END]:
            raise OpError("This device doesn't match the backup, because its update-mode code is different. Nothing was written.")
        mac = image.MAC_SECTOR
        if not image.same_unit(probe._read(ch, mode, mac, image.SECTOR), backup.data[mac:mac + image.SECTOR]):
            raise OpError("This backup is from another controller, because the address is different. Nothing was written.")
    except protocol.ProtocolError as e:
        raise OpError(f"{e}. Nothing was written.") from e


PENDING = "A firmware update is pending on this controller, and it could replace the tweaks the next time the controller starts. Nothing was written. Start the controller normally once, then check again."


def check_no_pending_update(ch, message: str = PENDING, mode: str = "boot") -> None:
    """A staged update could replace what is written at the next start (fields as in vomba/8bitdo-ultimate-2c-apple)."""
    try:
        pending = probe.pending_update(ch, mode)
    except protocol.ProtocolError as e:
        raise OpError(f"{e}. Nothing was written.") from e
    if pending:
        raise OpError(message)


def current_bank_a(ch, mode: str = "boot") -> bytes:
    try:
        return probe._read(ch, mode, image.BASE, image.APP_SIZE)
    except protocol.ProtocolError as e:
        raise OpError(f"{e}. Nothing was written.") from e


def plan_patch(ch, backup, stock: bytes, keys, mode: str = "boot") -> Plan:
    check_unit(ch, backup, mode)
    check_no_pending_update(ch, mode=mode)
    cur = current_bank_a(ch, mode)
    replacing = not recipes.identify(cur).known
    if replacing:  # the whole bank A is written from stock either way, so 1.09 is all that matters, as for Restore
        v, _ = probe.detect_version(ch, mode, cur)
        if v is None:
            raise OpError("This controller's firmware isn't the original 1.09, with or without this app's tweaks, and its version can't be identified, so nothing was written. It may be another firmware version, which you can update with 8BitDo's own updater, or firmware modified outside this app, which restoring your backup replaces.")
        if abs(v - image.SUPPORTED_VERSION) > 1e-6:
            raise OpError(f"This controller has firmware {v:.2f}, and this app only supports {image.SUPPORTED_VERSION:.2f}, so nothing was written. Update it with 8BitDo's own updater first.")
    try:
        new = recipes.build(stock, keys)
    except recipes.RecipeError as e:
        raise OpError(str(e)) from e
    target = bytearray(image.FLASH_SIZE)
    target[image.BASE:image.APP_END] = new
    diff = sum(x != y for x, y in zip(cur, new))
    note = "This replaces firmware 1.09 that this app doesn't recognise. " if replacing else ""
    tweaks = listed(recipes.RECIPES[k].title for k in shown(keys)) if shown(keys) else "no tweaks"
    return Plan(bytes(target), diff > 0, [], diff, f"{note}Installing changes {count(diff, 'byte')} of the firmware, with {tweaks}.")
