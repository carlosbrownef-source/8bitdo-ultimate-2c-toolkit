# SPDX-License-Identifier: GPL-3.0-or-later
"""Patch: stock v1.09 bank A plus tweaks, written through the bootloader."""
from .. import protocol
from ..firmware import image, recipes
from ..protocol import boot
from .plan import OpError, Plan, apply  # noqa: F401  (apply is part of this module's interface)


def check_unit(ch, backup) -> None:
    """The device in boot mode must be a controller with this backup's bootloader and MAC sector."""
    if len(backup.data) != image.FLASH_SIZE:
        raise OpError("the backup is not a full controller backup")
    try:
        if boot.kind(ch) != "controller":
            raise OpError("the device in update mode is not a controller (the 2.4 GHz dongle is not supported)")
        if boot.read(ch, 0, image.BOOT_END) != backup.data[:image.BOOT_END]:
            raise OpError("this device doesn't match the backup (its update-mode code differs); nothing written")
        mac = image.MAC_SECTOR
        if boot.read(ch, mac, image.SECTOR) != backup.data[mac:mac + image.SECTOR]:
            raise OpError("the backup is from another controller (its address differs); nothing written")
    except protocol.ProtocolError as e:
        raise OpError(f"{e}; nothing written") from e


def current_bank_a(ch) -> bytes:
    try:
        return boot.read(ch, image.BASE, image.BANK_A_SIZE)
    except protocol.ProtocolError as e:
        raise OpError(f"{e}; nothing written") from e


def plan_patch(ch, backup, stock: bytes, keys) -> Plan:
    check_unit(ch, backup)
    cur = current_bank_a(ch)
    if not recipes.identify(cur).known:
        raise OpError("this controller's firmware isn't the original 1.09, with or without the tweaks: use Restore first; nothing written")
    try:
        new = recipes.build(stock, keys)
    except recipes.RecipeError as e:
        raise OpError(str(e)) from e
    target = bytearray(image.FLASH_SIZE)
    target[image.BASE:image.BANK_A_END] = new
    target[image.BANK_A_END:image.BANK_A_ERASE_END] = b"\xff" * (image.BANK_A_ERASE_END - image.BANK_A_END)
    diff = sum(x != y for x, y in zip(cur, new))
    return Plan(bytes(target), diff > 0, [], diff, f"{diff} bytes of the firmware change; tweaks: {', '.join(recipes.RECIPES[k].title for k in keys) or 'none'}")
