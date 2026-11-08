# SPDX-License-Identifier: GPL-3.0-or-later
"""Patch: stock v1.09 bank A plus tweaks, written through the bootloader."""
from .. import protocol
from ..firmware import image, recipes
from ..protocol import boot
from . import probe
from .plan import OpError, Plan, apply, count  # noqa: F401  (apply is part of this module's interface)


def check_unit(ch, backup) -> None:
    """The device in boot mode must be a controller with this backup's bootloader and address."""
    if len(backup.data) != image.FLASH_SIZE:
        raise OpError("This isn't a full backup of the controller.")
    try:
        if boot.kind(ch) != "controller":
            raise OpError("The device in update mode isn't a controller. The 2.4 GHz dongle isn't supported.")
        if boot.read(ch, 0, image.BOOT_END) != backup.data[:image.BOOT_END]:
            raise OpError("This device doesn't match the backup, because its update-mode code is different. Nothing was written.")
        mac = image.MAC_SECTOR
        if not image.same_unit(boot.read(ch, mac, image.SECTOR), backup.data[mac:mac + image.SECTOR]):
            raise OpError("This backup is from another controller, because the address is different. Nothing was written.")
    except protocol.ProtocolError as e:
        raise OpError(f"{e}. Nothing was written.") from e


PENDING = "A firmware update is pending on this controller, and it could replace the tweaks the next time the controller starts. Nothing was written. Start the controller normally once, then check again."


def check_no_pending_update(ch, message: str = PENDING) -> None:
    """A staged update could replace what is written at the next start (fields as in vomba/8bitdo-ultimate-2c-apple)."""
    try:
        pending = probe.pending_update(ch, "boot")
    except protocol.ProtocolError as e:
        raise OpError(f"{e}. Nothing was written.") from e
    if pending:
        raise OpError(message)


def current_bank_a(ch) -> bytes:
    try:
        return boot.read(ch, image.BASE, image.APP_SIZE)
    except protocol.ProtocolError as e:
        raise OpError(f"{e}. Nothing was written.") from e


def plan_patch(ch, backup, stock: bytes, keys) -> Plan:
    check_unit(ch, backup)
    check_no_pending_update(ch)
    cur = current_bank_a(ch)
    replacing = not recipes.identify(cur).known
    if replacing:  # the whole bank A is written from stock either way, so 1.09 is all that matters, as for Restore
        v, _ = probe.detect_version(ch, "boot", cur)
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
    return Plan(bytes(target), diff > 0, [], diff, f"{note}{count(diff, 'byte')} of the firmware will change. Tweaks: {', '.join(recipes.RECIPES[k].title for k in keys) or 'none'}.")
