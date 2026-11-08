# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore: put back this unit's backup, or 8BitDo's stock v1.09 bank A."""
from .. import protocol
from ..firmware import image, recipes
from ..protocol import boot
from .backup import describe, taken
from .patch import check_no_pending_update, check_unit, current_bank_a
from .probe import detect_version
from .plan import OpError, Plan, count


def plan_restore(ch, backup, source: str, stock, force_unknown: bool = False) -> Plan:
    """Bank A may be in any state (this exists for damaged firmware); the unit checks still apply. Restoring stock also
    needs the firmware to be 1.09; force_unknown lets it proceed when the version cannot be determined (never when it is
    known to be another version)."""
    check_unit(ch, backup)
    if source not in ("backup", "stock"):
        raise OpError(f"unknown restore source {source!r}")
    cur = current_bank_a(ch)
    if source == "stock":  # a backup restore puts the update record back too, so only this one can be undone by it
        check_no_pending_update(ch, "A firmware update is pending on this controller, and it could replace the restored firmware the next time "
                                    "the controller starts. Nothing was written. Restoring your backup still works.")
        v, _ = detect_version(ch, "boot", cur)
        if v is None and not force_unknown:
            raise OpError("This controller's firmware version can't be identified, so nothing was written. Restoring your "
                          "own backup still works, or you can use \"Install Firmware 1.09 Anyway…\" in the Diagnostics tab if you accept the risk.")
        if v is not None and abs(v - image.SUPPORTED_VERSION) > 1e-6:
            raise OpError(f"This controller has firmware {v:.2f}, and this app only supports {image.SUPPORTED_VERSION:.2f}. "
                          "Update it with 8BitDo's own updater first. Restoring your own backup still works.")
    target = bytearray(backup.data)
    if source == "stock":
        if stock is None or len(stock) != image.BANK_A_SIZE:
            raise OpError("There's no original firmware 1.09 to restore.")
        target[image.BASE:image.APP_END] = recipes.whole(stock)
    want = bytes(target[image.BASE:image.APP_END])
    others = []
    if source == "backup":
        try:
            now = boot.read(ch, image.BANK_A_ERASE_END, image.CONFIG_START - image.BANK_A_ERASE_END)
        except protocol.ProtocolError as e:
            raise OpError(f"{e}. Nothing was written.") from e
        for a in range(image.BANK_A_ERASE_END, image.CONFIG_START, image.SECTOR):
            o = a - image.BANK_A_ERASE_END
            if now[o:o + image.SECTOR] != bytes(target[a:a + image.SECTOR]):
                others.append(a)
    diff = sum(x != y for x, y in zip(cur, want))
    what = (f"This restores the backup “{backup.path.name}”, made on {taken(backup.path)}, which has {describe(backup.state)}."
            if source == "backup" else "This installs 8BitDo's original firmware 1.09.")
    blocks = f" and {count(len(others), 'other block')} of the controller's memory" if others else ""
    return Plan(bytes(target), cur != want, others, diff, f"{what} It changes {count(diff, 'byte')} of the firmware{blocks}.")
