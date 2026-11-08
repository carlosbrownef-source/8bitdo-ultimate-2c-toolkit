# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import random
import unittest

from u2c_customfw.ops import dongle
from u2c_customfw.ops.plan import OpError
from u2c_customfw.sim import SimApp

rnd = random.Random(5)
STOCK = bytearray(rnd.randbytes(dongle.SIZE))
STOCK[dongle.DESC - dongle.BASE:dongle.DESC - dongle.BASE + 18] = dongle.STOCK_DESC
STOCK = bytes(STOCK)
XBOX = bytearray(STOCK)
XBOX[dongle.DESC - dongle.BASE:dongle.DESC - dongle.BASE + 18] = dongle.XBOX_DESC
XBOX = bytes(XBOX)
K = dict(stock_sha256=hashlib.sha256(STOCK).hexdigest(), xbox360_sha256=hashlib.sha256(XBOX).hexdigest())


def flash(bank_a: bytes, version: int = 0x67) -> bytes:
    f = bytearray(b"\xff" * 0x20000)
    f[dongle.BASE:dongle.BASE + dongle.SIZE] = bank_a
    f[dongle.RECORD + 0x0C] = version
    return bytes(f)


class DongleFirmwareTest(unittest.TestCase):
    def test_original_firmware(self):
        self.assertEqual(dongle.read_firmware(SimApp(flash(STOCK)), **K), dongle.DongleFirmware(True, 1.03, False))

    def test_xbox_360_tweak(self):
        self.assertEqual(dongle.read_firmware(SimApp(flash(XBOX)), **K), dongle.DongleFirmware(True, 1.03, True))

    def test_other_firmware_gives_the_version_of_its_record(self):
        self.assertEqual(dongle.read_firmware(SimApp(flash(rnd.randbytes(dongle.SIZE), 0x68)), **K), dongle.DongleFirmware(False, 1.04, False))

    def test_a_dongle_that_stops_answering_is_an_error(self):
        class Silent:
            def xfer(self, *a, **k):
                return None
        with self.assertRaises(OpError) as e:
            dongle.read_firmware(Silent(), **K)
        self.assertIn("dongle", str(e.exception))

    def test_the_real_hashes_are_set(self):
        self.assertEqual((len(dongle.STOCK_SHA256), len(dongle.XBOX360_SHA256)), (64, 64))


class PairedDongleTest(unittest.TestCase):
    def find(self, version):
        from unittest import mock
        from u2c_customfw import transport
        from u2c_customfw.ops import devices
        info = transport.DeviceInfo(0x045E, 0x028E, 0xFF7A, "USB", "8BitDo Ultimate 2C Wireless Controller", None, version)
        with mock.patch.object(transport, "list_devices", lambda: [info]):
            return [f.mode for f in devices.find()]

    def test_the_patched_dongle_is_told_from_the_controller_by_its_usb_version(self):
        self.assertEqual(self.find(0x0103), ["dongle_paired"])
        self.assertEqual(self.find(0x0114), ["cable_360"])

    def test_the_cli_refuses_the_paired_dongle(self):
        from unittest import mock
        from u2c_customfw import cli
        from u2c_customfw.ops import devices
        from u2c_customfw import transport
        info = transport.DeviceInfo(0x045E, 0x028E, 0xFF7A, "USB", "x", None, 0x0103)
        with mock.patch.object(cli, "find", lambda: [devices.Found(info, "dongle_paired")]):
            with self.assertRaises(cli.Exit) as e:
                cli.pick(("cable", "cable_360"))
        self.assertIn("2.4 GHz dongle", e.exception.msg)


class World:
    """One simulated dongle that can go from idle (301c) to its bootloader (3208) and back, sharing one flash."""
    def __init__(self, flash_bytes, start="dongle"):
        from u2c_customfw import transport
        self.flash, self.mode = bytearray(flash_bytes), start
        self.infos = {"dongle": transport.DeviceInfo(0x2DC8, 0x301C, 0xFFA0, "USB", "IDLE", None),
                      "boot": transport.DeviceInfo(0x2DC8, 0x3208, 0x8C, "USB", "boot", None)}
        self.sent = []

    def find(self):
        from u2c_customfw.ops import devices
        return [devices.Found(self.infos[self.mode], self.mode)]

    def open(self, info, rid):
        world = self
        if self.mode == "dongle":
            class Idle(SimApp):
                def xfer(self, req, timeout=0.5):
                    world.sent.append(req[:5].hex())
                    if req[:5] == b"\x81\x05\x00\x51\x00":
                        world.mode = "boot"
                        return None
                    self.flash = bytes(world.flash)
                    return SimApp.xfer(self, req, timeout)
            return Idle(bytes(self.flash))
        from u2c_customfw.sim import SimBoot

        class Boot(SimBoot):
            def xfer(self, r, timeout=0.5):
                if int.from_bytes(r[1:3], "little") == 7:
                    world.mode = "dongle"
                    return None
                return SimBoot.xfer(self, r, timeout)
        b = Boot(bytes(self.flash))
        b.f = self.flash
        return b


class DongleWriteTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        self.store = Path(tempfile.mkdtemp())
        self.full = bytearray(flash(STOCK))
        self.full[0:dongle.BOOT_END] = rnd.randbytes(dongle.BOOT_END)
        self.full[dongle.CAL:dongle.CAL + 0x40] = rnd.randbytes(0x40)
        self.full = bytes(self.full)
        for name, value in (("STOCK_SHA256", K["stock_sha256"]), ("XBOX360_SHA256", K["xbox360_sha256"])):
            p = mock.patch.object(dongle, name, value); p.start(); self.addCleanup(p.stop)

    def test_backup_reads_the_whole_dongle_twice_and_keeps_it(self):
        path = dongle.backup(SimApp(self.full), self.store, lambda *a: None)
        self.assertTrue(path.name.startswith("dongle-"))
        self.assertEqual(path.read_bytes(), self.full)
        self.assertEqual([p for p, _ in dongle.unit_backups(self.store, dongle.unit_of(self.full))], [path])
        other = bytearray(self.full); other[dongle.CAL] ^= 1
        self.assertEqual(dongle.unit_backups(self.store, dongle.unit_of(bytes(other))), [])   # another dongle's calibration

    def test_target_derives_either_firmware_from_a_known_bank(self):
        self.assertEqual(dongle.target(STOCK, True), XBOX)
        self.assertEqual(dongle.target(XBOX, False), STOCK)
        with self.assertRaises(OpError):
            dongle.target(rnd.randbytes(dongle.SIZE), True)

    def test_installing_enters_update_mode_writes_only_bank_a_and_comes_back(self):
        w = World(self.full)
        dongle.apply(w.find, w.open, self.full, XBOX, lambda *a: None, wait=0.01)
        self.assertEqual(bytes(w.flash[dongle.BASE:dongle.END]), XBOX)
        self.assertEqual(bytes(w.flash[:dongle.BASE]), self.full[:dongle.BASE])
        self.assertEqual(bytes(w.flash[dongle.END:]), self.full[dongle.END:])   # record, bank B, calibration, licence untouched
        self.assertIn("81050051 00".replace(" ", ""), w.sent)
        self.assertEqual(w.mode, "dongle")

    def test_a_dongle_already_in_update_mode_can_be_restored(self):
        broken = bytearray(self.full); broken[dongle.BASE:dongle.END] = b"\xff" * dongle.SIZE
        w = World(bytes(broken), start="boot")
        dongle.apply(w.find, w.open, self.full, STOCK, lambda *a: None, wait=0.01)
        self.assertEqual(bytes(w.flash[dongle.BASE:dongle.END]), STOCK)

    def test_another_dongles_bootloader_stops_the_write_before_erasing(self):
        w = World(self.full)
        other = bytearray(self.full); other[10] ^= 1
        with self.assertRaises(OpError) as e:
            dongle.apply(w.find, w.open, bytes(other), XBOX, lambda *a: None, wait=0.01)
        self.assertIn("nothing was written", str(e.exception))
        self.assertEqual(bytes(w.flash), self.full)

    def test_the_write_never_leaves_bank_a(self):
        with self.assertRaises(AssertionError):
            dongle.apply(None, None, self.full, STOCK + b"x", lambda *a: None)


class DongleCliTest(DongleWriteTest):
    def run_cmd(self, cmd, world, **kw):
        from types import SimpleNamespace
        from unittest import mock
        from u2c_customfw import cli, state
        state.accept(self.store)
        said = []
        args = SimpleNamespace(**{**dict(write=False, tweaks="", backup=None, download=False, source="backup", expect=None,
                                         accept_disclaimer=False, force_unknown=False), **kw})
        args.say, args.hint, args.progress = said.append, lambda t: None, lambda *a: None
        with mock.patch.object(cli, "find", world.find), mock.patch.object(cli, "open_channel", world.open), \
                mock.patch.object(dongle.time, "sleep", lambda s: None):
            cmd(args, self.store)
        return said

    def test_back_up_then_install_then_restore_the_original(self):
        from u2c_customfw import cli
        w = World(self.full)
        said = self.run_cmd(cli.cmd_backup, w)
        self.assertIn("The dongle has the original firmware 1.03.", said[-1])
        said = self.run_cmd(cli.cmd_patch, w, tweaks="dongle_360")
        self.assertTrue(said[-1].startswith("The check passed and nothing was written."), said)
        self.assertEqual(bytes(w.flash), self.full)   # a check only reads
        said = self.run_cmd(cli.cmd_patch, w, tweaks="dongle_360", write=True)
        self.assertEqual(bytes(w.flash[dongle.BASE:dongle.END]), XBOX)
        self.assertTrue(said[-1].startswith("Done."), said)
        self.run_cmd(cli.cmd_restore, w, source="stock", write=True)
        self.assertEqual(bytes(w.flash[dongle.BASE:dongle.END]), STOCK)

    def test_without_a_backup_nothing_is_written(self):
        from u2c_customfw import cli
        w = World(self.full)
        with self.assertRaises(cli.Exit) as e:
            self.run_cmd(cli.cmd_patch, w, tweaks="dongle_360", write=True)
        self.assertIn("no backup of this dongle", e.exception.msg)
        self.assertEqual(w.sent, [s for s in w.sent if s.startswith("810505")])   # only reads went out

    def test_a_dongle_left_in_update_mode_restores_its_backup(self):
        from u2c_customfw import cli
        w = World(self.full)
        self.run_cmd(cli.cmd_backup, w)
        w.flash[dongle.BASE:dongle.END] = b"\xff" * dongle.SIZE
        w.mode = "boot"
        self.run_cmd(cli.cmd_restore, w, source="backup", write=True)
        self.assertEqual(bytes(w.flash), self.full)
