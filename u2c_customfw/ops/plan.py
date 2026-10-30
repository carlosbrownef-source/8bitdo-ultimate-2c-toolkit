# SPDX-License-Identifier: GPL-3.0-or-later
"""A write plan and its execution: the stream proven on hardware, with the hard limits enforced here."""
from dataclasses import dataclass, field

from .. import protocol
from ..firmware import image
from ..protocol import boot

INTERRUPTED = "Interrupted: the controller may not start until this is finished. Use Diagnose > Restore (your backup or 8BitDo's v1.09); the bootloader is untouched."


class OpError(Exception):
    """An operation refused or failed; the message says why and what to do."""


@dataclass
class Plan:
    image: bytes                       # target flash image (only 0x6000-0x73000 is used)
    bank_a: bool                       # rewrite bank A (erase 0x6000-0x19000, write the payload)
    other_sectors: list = field(default_factory=list)   # 4 KB sectors outside bank A to erase and rewrite
    diff_bytes: int = 0
    summary: str = ""


def check_ranges(plan: Plan) -> None:
    for a in plan.other_sectors:
        if not (image.BANK_A_ERASE_END <= a < image.CONFIG_START) or a % image.SECTOR:
            raise OpError(f"refusing to write the sector at {a:#x}")


def _runs(sectors):
    out = []
    for a in sorted(sectors):
        if out and out[-1][1] == a:
            out[-1][1] = a + image.SECTOR
        else:
            out.append([a, a + image.SECTOR])
    return out


def apply(ch, plan: Plan, progress) -> None:
    check_ranges(plan)
    total = (image.BANK_A_SIZE if plan.bank_a else 0) + len(plan.other_sectors) * image.SECTOR
    done = 0
    try:
        if plan.bank_a:
            boot.erase(ch, image.BASE, image.BANK_A_ERASE_END - image.BASE)
            for a in range(image.BASE, image.BANK_A_END, boot.CHUNK):
                blk = plan.image[a:min(a + boot.CHUNK, image.BANK_A_END)]
                boot.write_chunk(ch, a, image.BANK_A_SIZE, blk)
                done += len(blk)
                progress("write", done, total)
            if boot.read(ch, image.BASE, image.BANK_A_ERASE_END - image.BASE) != plan.image[image.BASE:image.BANK_A_ERASE_END]:
                raise OpError("the read-back of bank A differs from what was written. " + INTERRUPTED)
        for lo, hi in _runs(plan.other_sectors):
            boot.erase(ch, lo, hi - lo)
            for a in range(lo, hi, boot.CHUNK):
                blk = plan.image[a:min(a + boot.CHUNK, hi)]
                if blk != b"\xff" * len(blk):
                    boot.write_chunk(ch, a, hi - lo, blk)
                done += len(blk)
                progress("write", done, total)
            if boot.read(ch, lo, hi - lo) != plan.image[lo:hi]:
                raise OpError(f"the read-back of {lo:#x}-{hi:#x} differs from what was written. " + INTERRUPTED)
    except protocol.ProtocolError as e:
        raise OpError(f"{e}. {INTERRUPTED}") from e
