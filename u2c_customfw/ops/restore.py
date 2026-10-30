# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore: put back this unit's backup, or 8BitDo's stock v1.09 bank A."""
from .. import protocol
from ..firmware import image
from ..protocol import boot
from .patch import check_unit, current_bank_a
from .plan import OpError, Plan


def plan_restore(ch, backup, source: str, stock) -> Plan:
    """Bank A may be in any state (this exists for damaged firmware); the unit checks still apply."""
    check_unit(ch, backup)
    if source not in ("backup", "stock"):
        raise OpError(f"unknown restore source {source!r}")
    cur = current_bank_a(ch)
    target = bytearray(backup.data)
    if source == "stock":
        if stock is None or len(stock) != image.BANK_A_SIZE:
            raise OpError("no stock v1.09 image to restore")
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
    return Plan(bytes(target), cur != want, others, diff, f"{diff} bytes of bank A differ; {len(others)} other sector(s) differ")
