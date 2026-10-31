# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore: put back this unit's backup, or 8BitDo's stock v1.09 bank A."""
from .. import protocol
from ..firmware import image
from ..protocol import boot
from .patch import check_unit, current_bank_a
from .probe import detect_version
from .plan import OpError, Plan


def plan_restore(ch, backup, source: str, stock, force_unknown: bool = False) -> Plan:
    """Bank A may be in any state (this exists for damaged firmware); the unit checks still apply. Restoring stock also
    needs the firmware to be 1.09; force_unknown lets it proceed when the version cannot be determined (never when it is
    known to be another version)."""
    check_unit(ch, backup)
    if source not in ("backup", "stock"):
        raise OpError(f"unknown restore source {source!r}")
    cur = current_bank_a(ch)
    if source == "stock":
        v, _ = detect_version(ch, "boot", cur)
        if v is None and not force_unknown:
            raise OpError("this controller's firmware version can't be identified, so nothing was written. Restoring your "
                          "own backup still works, or use \"Install firmware 1.09 anyway\" if you accept the risk.")
        if v is not None and abs(v - image.SUPPORTED_VERSION) > 1e-6:
            raise OpError(f"this controller has firmware {v:.2f}, and this app only supports {image.SUPPORTED_VERSION:.2f}: "
                          "update it with 8BitDo's own updater first (restoring your own backup still works)")
    target = bytearray(backup.data)
    if source == "stock":
        if stock is None or len(stock) != image.BANK_A_SIZE:
            raise OpError("no original firmware 1.09 to restore")
        target[image.BASE:image.BANK_A_END] = stock
    target[image.BANK_A_END:image.BANK_A_ERASE_END] = b"\xff" * (image.BANK_A_ERASE_END - image.BANK_A_END)
    want = bytes(target[image.BASE:image.BANK_A_END])
    others = []
    if source == "backup":
        try:
            now = boot.read(ch, image.BANK_A_ERASE_END, image.CONFIG_START - image.BANK_A_ERASE_END)
        except protocol.ProtocolError as e:
            raise OpError(f"{e}; nothing written") from e
        for a in range(image.BANK_A_ERASE_END, image.CONFIG_START, image.SECTOR):
            o = a - image.BANK_A_ERASE_END
            if now[o:o + image.SECTOR] != bytes(target[a:a + image.SECTOR]):
                others.append(a)
    diff = sum(x != y for x, y in zip(cur, want))
    return Plan(bytes(target), cur != want, others, diff, f"{diff} bytes of the firmware differ; {len(others)} other 4 KB block(s) differ")
