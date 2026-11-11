# SPDX-License-Identifier: GPL-3.0-or-later
"""Installing and restoring by cable: the app restarts the controller into update mode, and back afterwards."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from u2c_customfw import cli, state, transport
from u2c_customfw.firmware import image, recipes
from u2c_customfw.ops import devices
from u2c_customfw.sim import SimApp, SimBoot
from tests.test_cli import run
from tests.test_ops import K, STOCK_A, controller_flash

ENTER = "81050051" + "00"


class Controller:
    """One simulated controller, by cable (045e:028e) or in update mode (2dc8:3208), sharing one flash."""

    def __init__(self, flash, mode="cable_360", enters=True, comes_back=True, fail_after=None):
        self.flash, self.mode, self.enters, self.comes_back, self.fail_after = bytearray(flash), mode, enters, comes_back, fail_after
        self.sent, self.boot_cmds, self.ops = [], [], []
        self.infos = {"cable_360": transport.DeviceInfo(0x045E, 0x028E, 0x01, "USB", "8BitDo Ultimate 2C Wireless Controller", None),
                      "boot": transport.DeviceInfo(0x2DC8, 0x3208, 0x8C, "USB", "8BitDo Boot", None)}

    def find(self):
        return [devices.Found(self.infos[self.mode], self.mode)] if self.mode in self.infos else []

    def open(self, info, rid):
        unit = self
        if self.mode == "cable_360":
            class Running(SimApp):
                def xfer(self, req, timeout=0.5, accept=None):
                    unit.sent.append(req[:5].hex())
                    if req[:5] == bytes.fromhex(ENTER):
                        if unit.enters:
                            unit.mode = "boot"
                        return None
                    self.flash = bytes(unit.flash)
                    return SimApp.xfer(self, req, timeout)
            return Running(bytes(self.flash))

        class Boot(SimBoot):
            def xfer(self, r, timeout=0.5, accept=None):
                cmd = int.from_bytes(r[1:3], "little")
                unit.boot_cmds.append(cmd)
                if cmd == 7:
                    unit.mode = "cable_360" if unit.comes_back else "gone"
                    return None
                return SimBoot.xfer(self, r, timeout)
        b = Boot(bytes(self.flash), fail_after=self.fail_after)
        b.f, b.ops = self.flash, self.ops
        return b


def go(argv, unit, store):
    with mock.patch.object(cli, "BOOT_WAIT", 0.3), mock.patch.object(cli, "BACK_WAIT", 0.3), mock.patch.object(cli, "STEP", 0.01), \
            mock.patch.object(cli.fetch, "fetch_stock", lambda: STOCK_A):
        code, text = run(argv + ["--store", str(store)], None, None, find=unit.find, open_channel=unit.open)
    return code, text


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.flash = controller_flash()
        (self.tmp / "controller-20260101-000000.bin").write_bytes(self.flash)
        state.accept(self.tmp)

    def tweaked(self):
        return recipes.identify(bytes(self.unit.flash[image.BASE:image.BANK_A_END]), **K).recipes


class ByCableTest(Base):
    def test_installing_enters_update_mode_writes_and_restarts_the_controller(self):
        self.unit = Controller(self.flash)
        code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.tweaked(), ("ble_interval", "cable_360"))
        self.assertEqual(self.unit.sent.count(ENTER), 1)
        self.assertEqual(self.unit.boot_cmds.count(7), 1)
        self.assertEqual(self.unit.mode, "cable_360")
        self.assertTrue(text.rstrip().endswith("Installed. The controller restarted with its new firmware. If you changed a Bluetooth tweak, "
                                               "remove the controller in System Settings → Bluetooth and pair it again."), text)

    def test_restoring_the_original_by_cable_restarts_it_too(self):
        built = bytearray(self.flash)
        built[image.BASE:image.APP_END] = recipes.build(STOCK_A, ["cable_360"], **K)
        (self.tmp / "controller-20260101-000000.bin").write_bytes(bytes(built))
        self.unit = Controller(bytes(built))
        code, text = go(["restore", "stock", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertEqual(bytes(self.unit.flash[image.BASE:image.BANK_A_END]), STOCK_A)
        self.assertEqual(self.unit.mode, "cable_360")
        self.assertIn("Restored. The controller restarted with its new firmware.", text)

    def test_a_check_by_cable_reads_through_the_update_channel_and_leaves_it_running(self):
        self.unit = Controller(self.flash)
        code, text = go(["patch", "--tweaks", "cable_360"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertIn("The check passed and nothing was written.", text)
        self.assertNotIn(ENTER, self.unit.sent)
        self.assertEqual(self.unit.boot_cmds, [])
        self.assertEqual(self.unit.mode, "cable_360")

    def test_a_restore_check_by_cable_leaves_it_running_too(self):
        self.unit = Controller(self.flash)
        code, text = go(["restore", "backup"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertNotIn(ENTER, self.unit.sent)
        self.assertEqual(self.unit.mode, "cable_360")

    def test_nothing_to_change_leaves_it_running(self):
        built = bytearray(self.flash)
        built[image.BASE:image.APP_END] = recipes.build(STOCK_A, ["cable_360", "ble_interval"], **K)
        self.unit = Controller(bytes(built))
        code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertIn("The controller already has this firmware, so nothing was written.", text)
        self.assertNotIn(ENTER, self.unit.sent)
        self.assertEqual(self.unit.mode, "cable_360")

    def test_a_stop_before_writing_leaves_it_running(self):
        (self.tmp / "controller-20260101-000000.bin").unlink()   # no backup of this unit
        self.unit = Controller(self.flash)
        code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 2, text)
        self.assertIn("There's no backup of this controller.", text)
        self.assertNotIn(ENTER, self.unit.sent)
        self.assertEqual(self.unit.mode, "cable_360")

    def test_a_stop_in_update_mode_before_erasing_restarts_it(self):
        self.unit = Controller(self.flash)
        real = Controller.open

        def other_bootloader(unit, info, rid):
            ch = real(unit, info, rid)
            if unit.mode == "boot":
                ch.f[0:16] = b"\0" * 16   # its bootloader no longer matches the backup
            return ch
        with mock.patch.object(Controller, "open", other_bootloader):
            code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 2, text)
        self.assertIn("There's no backup of this controller.", text)   # found again by its bootloader, which changed
        self.assertEqual([o for o in self.unit.ops if o[0] in ("erase", "write")], [])
        self.assertEqual(self.unit.boot_cmds.count(7), 1)
        self.assertEqual(self.unit.mode, "cable_360")

    def test_a_write_that_fails_after_erasing_stays_in_update_mode_for_restore(self):
        self.unit = Controller(self.flash, fail_after=1)
        code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 1, text)
        self.assertIn("Use Restore", text)
        self.assertNotIn(7, self.unit.boot_cmds)
        self.assertEqual(self.unit.mode, "boot")

    def test_a_dongle_with_the_controllers_id_never_gets_the_command(self):
        dongle_like = bytearray(self.flash)
        dongle_like[0x10000:0x10010] = b"\xff" * 16
        self.unit = Controller(bytes(dongle_like))
        code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 1, text)
        self.assertIn("2.4 GHz dongle", text)
        self.assertNotIn(ENTER, self.unit.sent)
        self.assertEqual(self.unit.mode, "cable_360")

    def test_firmware_that_ignores_the_command_writes_nothing_and_says_how_to_enter_by_hand(self):
        self.unit = Controller(self.flash, enters=False)
        code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 2, text)
        self.assertIn("The controller didn't restart into update mode, so nothing was written.", text)
        self.assertIn("LB + RB", text)
        self.assertEqual(self.unit.ops, [])

    def test_a_controller_that_doesnt_come_back_gets_the_way_out(self):
        self.unit = Controller(self.flash, comes_back=False)
        code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertIn("Installed. The controller hasn't come back yet: if macOS asks whether to allow the accessory to connect, allow it.", text)


    def test_a_bootloader_that_cant_be_opened_says_where_the_controller_is(self):
        self.unit = Controller(self.flash)
        real = Controller.open

        def fails_in_boot(unit, info, rid):
            if unit.mode == "boot":
                raise OSError("could not open the device")
            return real(unit, info, rid)
        with mock.patch.object(Controller, "open", fails_in_boot):
            code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 1, text)
        self.assertIn("The controller is in update mode and nothing was written.", text)

    def test_a_restart_that_fails_doesnt_hide_a_good_install(self):
        self.unit = Controller(self.flash, comes_back=False)
        real = Controller.open

        def restart_fails(unit, info, rid):
            ch = real(unit, info, rid)
            if unit.mode == "boot":
                inner = ch.xfer

                def xfer(r, timeout=0.5, accept=None):
                    if int.from_bytes(r[1:3], "little") == 7:
                        raise OSError("gone")
                    return inner(r, timeout, accept)
                ch.xfer = xfer
            return ch
        with mock.patch.object(Controller, "open", restart_fails):
            code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.tweaked(), ("ble_interval", "cable_360"))
        self.assertIn("Installed. The controller hasn't come back yet", text)


class AlreadyInUpdateModeTest(Base):
    def test_a_check_leaves_it_in_update_mode(self):
        self.unit = Controller(self.flash, mode="boot")
        code, text = go(["patch", "--tweaks", "cable_360"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.unit.mode, "boot")
        self.assertNotIn(7, self.unit.boot_cmds)
        self.assertNotIn(ENTER, self.unit.sent)

    def test_a_write_restarts_it_with_its_new_firmware(self):
        self.unit = Controller(self.flash, mode="boot")
        code, text = go(["patch", "--tweaks", "cable_360", "--write"], self.unit, self.tmp)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.unit.mode, "cable_360")
        self.assertNotIn(ENTER, self.unit.sent)
        self.assertIn("Installed. The controller restarted with its new firmware.", text)


if __name__ == "__main__":
    unittest.main()
