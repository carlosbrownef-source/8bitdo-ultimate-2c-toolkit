# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line front end: devices, backup, identify, patch, restore, report."""
import argparse
import contextlib
import sys
from pathlib import Path

from . import fetch, state
from .firmware import image, recipes
from .ops import backup as bkp, devices, dongle as dng, patch, probe, report, restore, shown
from .ops.log import get_logger
from .ops.plan import OpError
from . import protocol
from .protocol import app, boot
from .transport import PermissionDenied, open_channel

CONTROLLER_MODES = ("cable", "cable_360", "boot", "dongle", "dongle_paired")
BOOT_HELP = "Turn the controller fully off, then hold LB + RB while plugging in the cable. The small light below the Home ring will blink white."
RESTARTED = "The controller restarted with its new firmware."
REPLUG = "Unplug the controller, hold Home for about 12 seconds until it turns off, then connect it again."
INSTALLED = "Installed. {} If you changed a Bluetooth tweak, remove the controller in System Settings → Bluetooth and pair it again."
RESTORED = "Restored. {} If its Bluetooth tweaks changed, remove the controller in System Settings → Bluetooth and pair it again."
NOT_ENTERED = "The controller didn't restart into update mode, so nothing was written. "
BOOT_WAIT, BACK_WAIT, STEP = 8, 10, 0.3   # seconds: to reach update mode, to come back from it, between looks
UNCHANGED = "The controller already has this firmware, so nothing was written."
CHECKED = "The check passed and nothing was written."
DONGLE_DONE = "Done. The dongle restarted with its new firmware. Turn the controller on to use it."
DONGLE_REPLUG = "Done. Unplug the dongle and plug it back in, then turn the controller on to use it."
DONGLE_ALONE = "Turn the controller off so the dongle is connected on its own, then try again. Nothing was written."
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
        if present and present[0].mode.startswith("dongle"):
            raise Exit(2, "That is the 2.4 GHz dongle, and this only works with the controller.")
        want = "by cable" if "cable" in modes else "in update mode. " + BOOT_HELP
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


def _dongle_in_boot(f) -> bool:
    """A device in update mode is the dongle when its bootloader says so."""
    if f.mode != "boot":
        return False
    ch = open_channel(f.info, 0)
    try:
        return boot.identify(ch) == boot.DONGLE_ID
    finally:
        ch.close()


def _dongle_change(args, store, f, xbox: bool | None, source: str | None = None):
    """Install (xbox: with the Xbox 360 change or not) or restore (source "backup" or "stock") the dongle's bank A."""
    if f.mode == "dongle_paired":
        raise Exit(2, DONGLE_ALONE)
    in_boot = f.mode == "boot"
    ch = open_channel(f.info, 0 if in_boot else 0x81)
    try:
        unit = dng.read_unit(ch, in_boot)
        try:
            cur = boot.read(ch, dng.BASE, dng.SIZE) if in_boot else dng._read(ch, dng.BASE, dng.SIZE)
        except protocol.ProtocolError as e:
            raise OpError(str(e)) from e
    finally:
        ch.close()
    found = dng.unit_backups(store, unit)
    if not found:
        raise Exit(2, "There's no backup of this dongle. Back it up first, with the dongle connected on its own.")
    if source == "backup":
        pick_ = next(((p, d) for p, d in found if dng.state(d[dng.BASE:dng.END])[0]), None)
        if pick_ is None:
            raise Exit(2, "None of this dongle's backups has firmware this app recognises, so nothing was written. "
                          "You can restore the original firmware 1.03 instead.")
        if getattr(args, "expect", None) and pick_[0].name != args.expect:
            raise Exit(2, "The backup to restore isn't the one shown, so nothing was written. Check again.")
        new = pick_[1][dng.BASE:dng.END]
        what = f"This restores the dongle's backup “{pick_[0].name}”, made on {bkp.taken(pick_[0])}."
    else:
        base = cur if dng.state(cur)[0] else next((d[dng.BASE:dng.END] for _, d in found if dng.state(d[dng.BASE:dng.END])[0]), None)
        if base is None:
            raise Exit(2, "Neither the dongle nor its backups hold firmware this app recognises, so nothing was written.")
        new = dng.target(base, bool(xbox))
        what = (f"This installs firmware 1.03 with {dng.TITLE} on the dongle." if xbox
                else "This installs 8BitDo's original firmware 1.03 on the dongle.")
    if cur == new:
        args.unchanged = True
        args.say("The dongle already has this firmware, so nothing was written.")
        return
    diff = sum(x != y for x, y in zip(cur, new))
    summary = (f"{what} It changes {patch.count(diff, 'byte')} of its firmware. The app restarts the dongle into update mode to "
               "write, and checks it there again before erasing anything.")
    if not args.write:
        args.say(f"{CHECKED} {summary}")
        args.hint("Add --write to write it.")
        return
    args.say(summary)
    came_back = dng.apply(find, open_channel, found[0][1], new, args.progress)
    args.say(DONGLE_DONE if came_back else DONGLE_REPLUG)


def cmd_backup(args, store):
    f = pick(("cable", "cable_360", "boot", "dongle", "dongle_paired"))
    if f.mode.startswith("dongle"):
        ch = open_channel(f.info, 0x81)
        try:
            path = dng.backup(ch, store, args.progress)
        finally:
            ch.close()
        known, xbox = dng.state(path.read_bytes()[dng.BASE:dng.END])
        get_logger(store).info("backup %s", path.name)
        args.hint(str(path))
        has = (f"firmware 1.03 with {dng.TITLE}" if xbox else "the original firmware 1.03") if known else "firmware this app doesn't recognise"
        args.say(f"Backup saved as “{path.name}”. The dongle has {has}.")
        return
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
    args.say(("original 1.09" + (f" with tweaks: {', '.join(shown(s.recipes))}" if shown(s.recipes) else "")) if s.known else "unknown firmware")


def unit_backups(ch, store, mode="boot"):
    """The backups of the controller on ch, in update mode or by cable, newest first."""
    return bkp.find_backups(store, probe._read(ch, mode, 0, image.BOOT_END), probe._read(ch, mode, image.MAC_SECTOR, image.SECTOR))


def _backup_for(args, ch, store, recognised=False, mode="boot"):
    """The backup named with --backup, or the newest of this unit; recognised: the newest whose firmware the app
    recognises, which is the one Restore puts back."""
    if args.backup:
        return bkp.load(Path(args.backup))
    found = unit_backups(ch, store, mode)
    if not found:
        raise Exit(2, "There's no backup of this controller. Back it up first, connected by cable.")
    if not recognised:
        return found[0]
    b = bkp.restorable(found)
    if b is None:
        raise Exit(2, "None of this controller's backups has firmware this app recognises, so nothing was written. "
                      "You can restore the original firmware 1.09 instead.")
    return b


def _write(args, ch, plan, hint):
    """Write the plan unless it's a check or changes nothing; True if it wrote. args.erasing marks that a write has begun."""
    if not plan.bank_a and not plan.other_sectors:
        args.unchanged = True
        args.say(UNCHANGED)
        return False
    if not args.write:
        args.say(f"{CHECKED} {plan.summary}")
        args.hint(hint)
        return False
    args.say(plan.summary)
    args.erasing = True
    patch.apply(ch, plan, args.progress)
    args.wrote = True
    return True


def _into_update_mode(f):
    """By cable: restart the controller into update mode, once the update channel shows it isn't the dongle (a paired dongle
    has the controller's USB ID). Returns the bootloader's device."""
    ch = open_channel(f.info, 0x81)
    try:
        probe._check_device(ch, f.mode, None)
        app.enter_update_mode(ch)
    finally:
        ch.close()
    info = dng._wait(find, "boot", BOOT_WAIT, STEP)
    if info is None:
        raise Exit(2, NOT_ENTERED + BOOT_HELP)
    return info


def _back(mode_found=lambda: [f for f in find() if f.mode in ("cable", "cable_360")]):
    """Whether the controller came back by cable after the bootloader restarted it."""
    import time
    end = time.time() + BACK_WAIT
    while time.time() < end:
        if mode_found():
            return True
        time.sleep(STEP)
    return False


@contextlib.contextmanager
def _update_mode(args, f):
    """The bootloader's channel. By cable, the app puts the controller in update mode first. Afterwards the bootloader's
    restart command (7) starts the firmware, unless a write began and failed, which leaves it there for Restore; a controller
    that was already in update mode and got nothing written stays there too. args.back says whether it came back by cable."""
    entered = f.mode != "boot"
    ch = open_channel(_into_update_mode(f) if entered else f.info, 0)
    args.erasing, args.wrote, args.back, restart = False, False, None, False
    try:
        yield ch
        restart = entered or args.wrote
    except BaseException:
        restart = entered and not args.erasing
        raise
    finally:
        try:
            if restart:
                ch.xfer(boot.request(7), 0.5)
        finally:
            ch.close()
        if restart:
            args.back = _back()


def _plan_and_write(args, f, plan, hint, done):
    """By cable, check through the update channel, as for the dongle, so a check leaves the controller as it is. Only to write
    something, put it in update mode, check again there and write; then it restarts (see _update_mode)."""
    if f.mode != "boot":
        ch = open_channel(f.info, 0x81)
        try:
            probe._check_device(ch, f.mode, None)
            first = plan(ch, f.mode)
        finally:
            ch.close()
        if not args.write or (not first.bank_a and not first.other_sectors):
            _write(args, None, first, hint)
            return
    with _update_mode(args, f) as ch:
        wrote = _write(args, ch, plan(ch, "boot"), hint)
    if wrote:
        args.say(done.format(RESTARTED if args.back else REPLUG))


def cmd_patch(args, store):
    need_accept(args, store)
    f = pick(("boot", "cable", "cable_360", "dongle", "dongle_paired"))
    if f.mode.startswith("dongle") or _dongle_in_boot(f):
        return _dongle_change(args, store, f, xbox="dongle_360" in args.tweaks.split(","))
    keys = [k for k in args.tweaks.split(",") if k]
    keys += ["ble_interval"] if keys and "ble_interval" not in keys else []   # as the app: every install asks for 12.5 ms
    stock = {}

    def plan(ch, mode):
        b = _backup_for(args, ch, store, mode=mode)
        if "x" not in stock:
            stock["x"] = stock_for(args, b, store)
        return patch.plan_patch(ch, b, stock["x"], keys, mode)
    _plan_and_write(args, f, plan, "Add --write to install.", INSTALLED)


def cmd_restore(args, store):
    need_accept(args, store)
    f = pick(("boot", "cable", "cable_360", "dongle", "dongle_paired"))
    if f.mode.startswith("dongle") or _dongle_in_boot(f):
        return _dongle_change(args, store, f, xbox=None, source=args.source)
    stock = fetch.fetch_stock() if args.source == "stock" else None   # before update mode: a failed download leaves it as it was

    def plan(ch, mode):
        b = _backup_for(args, ch, store, recognised=args.source == "backup", mode=mode)
        if args.source == "backup" and getattr(args, "expect", None) and b.path.name != args.expect:  # the page names the backup it showed
            raise Exit(2, "The backup to restore isn't the one shown, so nothing was written. Check again.")
        return restore.plan_restore(ch, b, args.source, stock, args.force_unknown, mode)
    _plan_and_write(args, f, plan, "Add --write to restore.", RESTORED)


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
