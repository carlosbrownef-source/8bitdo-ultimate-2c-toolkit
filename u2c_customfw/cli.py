# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line front end: devices, backup, identify, patch, restore, report."""
import argparse
import sys
from pathlib import Path

from . import fetch, state
from .firmware import image, recipes
from .ops import backup as bkp, devices, patch, report, restore, shown
from .ops.log import get_logger
from .ops.plan import OpError
from . import protocol
from .protocol import boot
from .transport import PermissionDenied, open_channel

CONTROLLER_MODES = ("cable", "cable_360", "boot", "dongle")
BOOT_HELP = "Turn the controller fully off, then hold LB + RB while plugging in the cable. The light will blink white."
INSTALLED = ("Installed. Unplug the controller and connect it again. If you changed a Bluetooth tweak, remove the controller in "
             "System Settings → Bluetooth and pair it again.")
RESTORED = ("Restored. Unplug the controller and connect it again. If its Bluetooth tweaks changed, remove the controller in "
            "System Settings → Bluetooth and pair it again.")
UNCHANGED = "The controller already has this firmware, so nothing was written."
CHECKED = "The check passed and nothing was written."
DISCLAIMER_HELP = ("Read DISCLAIMER.md first. There's no warranty. Installing modified firmware probably voids the controller's warranty. It only works with the Ultimate 2C on firmware 1.09. "
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
    def __init__(self, code, msg, hint=""):
        self.code, self.msg, self.hint = code, msg, hint   # hint: command-line advice, printed by main() only, never shown in the app


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


def stock_for(args, backup, store):
    if args.download:
        return fetch.fetch_stock()
    stock = bkp.find_original(backup, store)
    if stock is None:
        raise Exit(2, "None of your backups contains the original firmware 1.09. Download it from 8BitDo's server instead.", "Or run this command again with --download.")
    return stock


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
    get_logger(store).info("backup %s sha256 %s", b.path.name, b.sha256)   # the name only: the folder holds the user's name
    args.hint(f"{b.path}\nsha256 {b.sha256}")
    args.say(f"Backup saved as “{b.path.name}”. The controller has {bkp.describe(b.state)}.")


def cmd_identify(args, store):
    data = Path(args.file).read_bytes()
    bank_a = data[image.BASE:image.APP_END] if len(data) == image.FLASH_SIZE else data
    s = recipes.identify(bank_a)
    args.say(("original 1.09" + (f" with tweaks: {', '.join(s.recipes)}" if s.recipes else "")) if s.known else "unknown firmware")


def unit_backups(ch, store):
    """The backups of the controller in update mode on ch, newest first."""
    return bkp.find_backups(store, boot.read(ch, 0, image.BOOT_END), boot.read(ch, image.MAC_SECTOR, image.SECTOR))


def _backup_for(args, ch, store, recognised=False):
    """The backup named with --backup, or the newest of this unit; recognised: the newest whose firmware the app
    recognises, which is the one Restore puts back."""
    if args.backup:
        return bkp.load(Path(args.backup))
    found = unit_backups(ch, store)
    if not found:
        raise Exit(2, "There's no backup of this controller. Back it up first, connected by cable.")
    if not recognised:
        return found[0]
    b = bkp.restorable(found)
    if b is None:
        raise Exit(2, "None of this controller's backups has firmware this app recognises, so nothing was written. "
                      "You can restore the original firmware 1.09 instead.")
    return b


def _write(args, ch, plan, done, hint):
    """Write the plan unless it's a check or changes nothing, and end with the sentence the app shows as the result."""
    if not plan.bank_a and not plan.other_sectors:
        args.unchanged = True
        args.say(UNCHANGED)
        return
    if not args.write:
        args.say(f"{CHECKED} {plan.summary}")
        args.hint(hint)
        return
    args.say(plan.summary)
    patch.apply(ch, plan, args.progress)
    args.say(done)


def cmd_patch(args, store):
    need_accept(args, store)
    f = pick(("boot",))
    ch = open_channel(f.info, 0)
    try:
        b = _backup_for(args, ch, store)
        plan = patch.plan_patch(ch, b, stock_for(args, b, store), [k for k in args.tweaks.split(",") if k])
        _write(args, ch, plan, INSTALLED, "Add --write to install.")
    finally:
        ch.close()


def cmd_restore(args, store):
    need_accept(args, store)
    f = pick(("boot",))
    ch = open_channel(f.info, 0)
    try:
        b = _backup_for(args, ch, store, recognised=args.source == "backup")
        if args.source == "backup" and getattr(args, "expect", None) and b.path.name != args.expect:  # the page names the backup it showed
            raise Exit(2, "The backup to restore isn't the one shown, so nothing was written. Check again.")
        stock = fetch.fetch_stock() if args.source == "stock" else None
        plan = restore.plan_restore(ch, b, args.source, stock, args.force_unknown)
        _write(args, ch, plan, RESTORED, "Add --write to restore.")
    finally:
        ch.close()


def cmd_report(args, store):
    tail = report.log_tail(store)
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
    p.add_argument("--tweaks", default="", help="comma list of: " + ", ".join(shown(k for k, r in recipes.RECIPES.items() if not r.earlier_form_of)))
    p.add_argument("--backup"); p.add_argument("--download", action="store_true", help="use 8BitDo's v1.09 from its server")
    p = sub.add_parser("restore", parents=[common])
    p.add_argument("source", choices=["backup", "stock"])
    p.add_argument("--backup", help="this backup file instead of the newest recognised one of the controller")
    p.add_argument("--force-unknown", action="store_true", help="restore 8BitDo's v1.09 even though the firmware version cannot be determined (risky)")
    for p in sub.choices.values():
        if p.prog.endswith(("patch", "restore")):
            p.add_argument("--write", action="store_true"); p.add_argument("--accept-disclaimer", action="store_true")
    args = ap.parse_args(argv)
    args.say, args.hint, args.progress = print, print, Bar()
    store = args.store or state.default_store()
    get_logger(store).info("command %s", args.cmd)
    lock = None
    try:
        if args.cmd in ("devices", "backup", "patch", "restore"):
            lock = state.lock_device(store)
            if lock is None:
                raise Exit(2, "Another copy of the app, or the command line, is using the controller. Wait until it finishes, then try again.")
        {"devices": cmd_devices, "backup": cmd_backup, "identify": cmd_identify, "patch": cmd_patch,
         "restore": cmd_restore, "report": cmd_report}[args.cmd](args, store)
    except Exit as e:
        print(f"{e.msg} {e.hint}".strip(), file=sys.stderr)
        return e.code
    except (OpError, fetch.FetchError, protocol.ProtocolError, PermissionDenied, OSError, NotImplementedError) as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1
    finally:
        if lock:
            state.unlock_device(lock)
    return 0
