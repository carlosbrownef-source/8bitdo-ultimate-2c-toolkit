# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line front end: devices, backup, identify, patch, restore, report."""
import argparse
import sys
from pathlib import Path

from . import fetch, state
from .firmware import image, recipes
from .ops import backup as bkp, devices, patch, report, restore
from .ops.log import get_logger
from .ops.plan import OpError
from . import protocol
from .protocol import boot
from .transport import PermissionDenied, open_channel

CONTROLLER_MODES = ("cable", "cable_360", "boot", "dongle")
BOOT_HELP = "Turn the controller fully off, then hold L1 + R1 while plugging in the cable. The light will blink white."
DISCLAIMER_HELP = ("Read DISCLAIMER.md first. There's no warranty, using this voids the controller's warranty, and it only works with the Ultimate 2C on firmware 1.09. "
                   "To write to the controller, add --accept-disclaimer once.")


def find():
    return devices.find()


class Bar:
    def __init__(self):
        self.last = {}

    def __call__(self, label, done, total):
        p = min(100, done * 100 // max(total, 1)) // 10 * 10
        if self.last.get(label) != p:
            self.last[label] = p
            print(f"[{'#' * (p // 10)}{'-' * (10 - p // 10)}] {p:3d} % {label}", flush=True)


class Exit(Exception):
    def __init__(self, code, msg):
        self.code, self.msg = code, msg


def pick(modes=CONTROLLER_MODES):
    present = [f for f in find() if f.mode in CONTROLLER_MODES]
    if len(present) > 1:
        raise Exit(2, "More than one device is connected. Unplug all but one controller.")
    if not present or present[0].mode not in modes:
        if present and present[0].mode == "dongle":
            raise Exit(2, "That is the 2.4 GHz dongle, which this app does not support.")
        want = "in update mode. " + BOOT_HELP if modes == ("boot",) else "by cable"
        raise Exit(2, f"No controller found {want}")
    return present[0]


def stock_for(args, backup):
    if args.download:
        return fetch.fetch_stock()
    if backup.state.known and not backup.state.recipes:
        return backup.data[image.BASE:image.BANK_A_END]
    raise Exit(2, "Your backup doesn't contain the original firmware 1.09. Download it from 8BitDo instead (--download).")


def need_accept(args, store):
    if args.write and not state.accepted(store):
        if not args.accept_disclaimer:
            raise Exit(2, "You haven't accepted the disclaimer yet. " + DISCLAIMER_HELP)
        state.accept(store)


def cmd_devices(args, store):
    for f in find():
        i = f.info
        args.say(f"{f.mode:15} {i.vendor:04x}:{i.product:04x} {i.name!r}")
        if f.mode == "boot":
            ch = open_channel(i, 0)
            try:
                who = boot.identify(ch)
            finally:
                ch.close()
            args.say(f"{'':15} identifies as {who:#06x}" if who is not None else f"{'':15} doesn't answer the identity query")


def cmd_backup(args, store):
    f = pick(("cable", "cable_360", "boot"))
    ch = open_channel(f.info, 0 if f.mode == "boot" else 0x81)
    try:
        b = bkp.backup(ch, f.mode, store, args.progress)
    finally:
        ch.close()
    s = b.state
    args.say(f"saved {b.path}\nsha256 {b.sha256}\nfirmware: " + (("original 1.09" + (f" with tweaks: {', '.join(s.recipes)}" if s.recipes else "")) if s.known else "unknown"))


def cmd_identify(args, store):
    data = Path(args.file).read_bytes()
    bank_a = data[image.BASE:image.BANK_A_END] if len(data) == image.FLASH_SIZE else data
    s = recipes.identify(bank_a)
    args.say(("original 1.09" + (f" with tweaks: {', '.join(s.recipes)}" if s.recipes else "")) if s.known else "unknown firmware")


def _backup_for(args, ch, store):
    from .protocol import boot
    if args.backup:
        return bkp.load(Path(args.backup))
    found = bkp.find_backups(store, boot.read(ch, 0, image.BOOT_END), boot.read(ch, image.MAC_SECTOR, image.SECTOR))
    if not found:
        raise Exit(2, "There's no backup of this controller. Back it up first, connected by cable.")
    return found[0]


def cmd_patch(args, store):
    need_accept(args, store)
    f = pick(("boot",))
    ch = open_channel(f.info, 0)
    try:
        b = _backup_for(args, ch, store)
        plan = patch.plan_patch(ch, b, stock_for(args, b), [k for k in args.tweaks.split(",") if k])
        args.say(plan.summary)
        if not args.write:
            args.say("The check passed. This was a dry run, so nothing was written. Add --write to install.")
            return
        patch.apply(ch, plan, args.progress)
        args.say("Done. Unplug the controller and plug it back in. If a Bluetooth tweak changed, remove the controller from Bluetooth settings and pair it again.")
    finally:
        ch.close()


def cmd_restore(args, store):
    need_accept(args, store)
    f = pick(("boot",))
    ch = open_channel(f.info, 0)
    try:
        b = bkp.load(Path(args.file)) if args.file else _backup_for(args, ch, store)
        stock = fetch.fetch_stock() if args.source == "stock" else None
        plan = restore.plan_restore(ch, b, args.source, stock, args.force_unknown)
        args.say(plan.summary)
        if not args.write:
            args.say("The check passed. This was a dry run, so nothing was written. Add --write to restore.")
            return
        patch.apply(ch, plan, args.progress)
        args.say("Done. Unplug the controller and plug it back in.")
    finally:
        ch.close()


def cmd_report(args, store):
    log = store / "u2c-customfw.log"
    tail = "\n".join(log.read_text().splitlines()[-30:]) if log.exists() else ""
    backups = sorted(Path(store).glob("controller-*.bin"))
    st = None
    if backups:
        try:
            st = bkp.load(backups[-1]).state   # the state at the newest backup, not a live read
        except OpError:
            pass
    args.say(report.report(find(), st, tail) + ("(firmware state is from the newest backup)\n" if st else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="u2c-customfw", description="Back up, patch and repair an 8BitDo Ultimate 2C (firmware 1.09).")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--store", type=Path, default=None, help="where backups and the log live")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices", parents=[common])
    sub.add_parser("backup", parents=[common])
    sub.add_parser("report", parents=[common])
    p = sub.add_parser("identify", parents=[common]); p.add_argument("file")
    p = sub.add_parser("patch", parents=[common])
    p.add_argument("--tweaks", default="", help="comma list of: " + ", ".join(recipes.RECIPES))
    p.add_argument("--backup"); p.add_argument("--download", action="store_true", help="use 8BitDo's v1.09 from its server")
    p = sub.add_parser("restore", parents=[common])
    p.add_argument("source", choices=["backup", "stock"]); p.add_argument("file", nargs="?")
    p.add_argument("--backup"); p.add_argument("--download", action="store_true")
    p.add_argument("--force-unknown", action="store_true", help="restore 8BitDo's v1.09 even though the firmware version cannot be determined (risky)")
    for p in sub.choices.values():
        if p.prog.endswith(("patch", "restore")):
            p.add_argument("--write", action="store_true"); p.add_argument("--accept-disclaimer", action="store_true")
    args = ap.parse_args(argv)
    args.say, args.progress = print, Bar()
    store = args.store or state.default_store()
    get_logger(store).info("command %s", args.cmd)
    try:
        {"devices": cmd_devices, "backup": cmd_backup, "identify": cmd_identify, "patch": cmd_patch,
         "restore": cmd_restore, "report": cmd_report}[args.cmd](args, store)
    except Exit as e:
        print(e.msg, file=sys.stderr)
        return e.code
    except (OpError, fetch.FetchError, protocol.ProtocolError, PermissionDenied) as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1
    return 0
