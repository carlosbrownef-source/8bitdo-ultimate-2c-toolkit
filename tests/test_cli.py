# SPDX-License-Identifier: GPL-3.0-or-later
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from u2c_customfw import cli, state, transport
from u2c_customfw.firmware import image, recipes
from u2c_customfw.ops import devices
from u2c_customfw.sim import SimApp, SimBoot
from tests.test_ops import K, STOCK_A, controller_flash


def found(mode, product=0x310A, page=0xFF7A):
    return devices.Found(transport.DeviceInfo(0x2DC8, product, page, "USB", "x", None), mode)


def run(argv, listing, channel=None):
    out = io.StringIO()
    with mock.patch.object(state, "default_store", lambda: Path(tempfile.mkdtemp())), mock.patch.object(cli, "find", lambda: listing), mock.patch.object(cli, "open_channel", lambda info, rid: channel), \
            mock.patch.object(recipes, "_constants", lambda a=None, b=None, c=None: (K["stock_sha256"], K["region_sha256"], K["remainder_sha256"])), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(argv)
    return code, out.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.flash = controller_flash()
        (self.tmp / "controller-20260101-000000.bin").write_bytes(self.flash)

    def test_devices_shows_what_the_bootloader_identifies_as(self):
        code, text = run(["devices", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], SimBoot(self.flash))
        self.assertEqual(code, 0)
        self.assertIn("0x301b", text)

    def test_identify_names_the_tweaks(self):
        built = recipes.build(STOCK_A, ["bt_xbox", "cable_360"], **K)
        f = bytearray(self.flash); f[image.BASE:image.APP_END] = built
        p = self.tmp / "x.bin"; p.write_bytes(bytes(f))
        code, text = run(["identify", str(p)], [])
        self.assertEqual(code, 0)
        self.assertIn("bt_xbox", text)
        self.assertIn("cable_360", text)

    def test_two_devices_exit_2(self):
        code, text = run(["backup", "--store", str(self.tmp)], [found("cable"), found("dongle", 0x301C, 0xFFA0)])
        self.assertEqual(code, 2)
        self.assertIn("More than one device is connected. Unplug all but one controller.", text)

    def test_two_units_in_the_same_mode_exit_2(self):
        a = found("boot", 0x3208, 0x8C)
        code, text = run(["patch", "--tweaks", "cable_360", "--store", str(self.tmp)], [a, found("boot", 0x3208, 0x8C)], SimBoot(self.flash))
        self.assertEqual(code, 2)
        self.assertIn("More than one device", text)

    def test_protocol_errors_are_messages_not_tracebacks(self):
        class Dead(SimBoot):
            def xfer(self, r, timeout=0.5, accept=None):
                return None
        code, text = run(["patch", "--tweaks", "cable_360", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], Dead(self.flash))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", text)

    def test_os_errors_are_messages_not_tracebacks(self):
        def opened_elsewhere(info, rid):
            raise OSError("The device couldn't be opened (IOReturn 0xe00002c5).")

        def linux():
            raise NotImplementedError("No transport for this platform yet. See docs/porting.md.")
        missing = str(self.tmp / "missing.bin")
        for argv, finder, opener in ((["identify", missing], lambda: [], None),
                                     (["patch", "--backup", missing], lambda: [found("boot", 0x3208, 0x8C)], lambda i, rid: SimBoot(self.flash)),
                                     (["backup"], lambda: [found("cable")], opened_elsewhere),
                                     (["backup"], linux, None)):
            with mock.patch.object(state, "default_store", lambda: self.tmp), mock.patch.object(cli, "find", finder), \
                    mock.patch.object(cli, "open_channel", opener), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(cli.main(argv), 1, argv)
            self.assertTrue(err.getvalue().startswith("stopped: "), err.getvalue())

    def test_patch_without_write_makes_no_erase_or_write(self):
        dev = SimBoot(self.flash)
        code, text = run(["patch", "--tweaks", "cable_360", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], dev)
        self.assertEqual(code, 0, text)
        self.assertIn("The check passed and nothing was written. Installing changes", text)
        self.assertIn("with Xbox 360 controller over cable.", text)
        self.assertIn("--write", text)
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])

    def test_write_needs_the_disclaimer_accepted(self):
        dev = SimBoot(self.flash)
        code, text = run(["patch", "--tweaks", "cable_360", "--write", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], dev)
        self.assertEqual(code, 2)
        self.assertIn("disclaimer", text.lower())
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])

    def test_write_after_accepting(self):
        state.accept(self.tmp)
        dev = SimBoot(self.flash)
        code, text = run(["patch", "--tweaks", "cable_360", "--write", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], dev)
        self.assertEqual(code, 0, text)
        self.assertEqual(recipes.identify(bytes(dev.f[0x6000:0x18400]), **K).recipes, ("ble_interval", "cable_360"))   # every install asks for 12.5 ms
        self.assertTrue(text.rstrip().endswith("Installed. Unplug the controller and connect it again. If you changed a Bluetooth tweak, "
                                               "remove the controller in System Settings → Bluetooth and pair it again."), text)

    def test_backup_says_what_it_saved_in_a_sentence(self):
        code, text = run(["backup", "--store", str(self.tmp)], [found("cable")], SimApp(self.flash))
        self.assertEqual(code, 0, text)
        self.assertRegex(text, r"Backup saved as “controller-\d{8}-\d{6}\.bin”\. The controller has the original firmware 1\.09\.")
        self.assertIn("sha256 ", text)   # for the command line only

    def test_installing_what_is_there_writes_nothing_and_says_so(self):
        state.accept(self.tmp)
        built = recipes.build(STOCK_A, ["cable_360", "ble_interval"], **K)
        f = bytearray(self.flash); f[image.BASE:image.APP_END] = built
        dev = SimBoot(bytes(f))
        code, text = run(["patch", "--tweaks", "cable_360", "--write", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], dev)
        self.assertEqual(code, 0, text)
        self.assertIn("The controller already has this firmware, so nothing was written.", text)
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])

    def test_report_uses_the_newest_backups_firmware_state(self):
        code, text = run(["report", "--store", str(self.tmp)], [found("cable")])
        self.assertEqual(code, 0)
        self.assertIn("Firmware: original 1.09", text)
        self.assertNotIn("not read", text)

    def test_restore_stock_accepts_force_unknown(self):
        dev = SimBoot(self.flash)
        code, text = run(["restore", "stock", "--force-unknown", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], dev)
        self.assertNotEqual(code, 2, text)   # 2 would be a usage error
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])

    def unrecognised(self):  # the same unit, with bank A no longer recognised (an interrupted install, say)
        f = bytearray(self.flash)
        f[image.BASE:image.BASE + 0x1000] = b"\xff" * 0x1000
        return bytes(f)

    def test_restore_backup_skips_a_newer_backup_it_doesnt_recognise(self):
        (self.tmp / "controller-20260102-000000.bin").write_bytes(self.unrecognised())
        code, text = run(["restore", "backup", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], SimBoot(self.unrecognised()))
        self.assertEqual(code, 0, text)
        self.assertIn("controller-20260101-000000.bin", text)
        self.assertIn("1 Jan 2026 at 00:00", text)
        self.assertIn("the original firmware 1.09", text)
        self.assertNotIn("controller-20260102-000000.bin", text)

    def test_restore_backup_refuses_when_no_backup_is_recognised(self):
        (self.tmp / "controller-20260101-000000.bin").write_bytes(self.unrecognised())
        dev = SimBoot(self.unrecognised())
        code, text = run(["restore", "backup", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], dev)
        self.assertEqual(code, 2)
        self.assertIn("None of this controller's backups has firmware this app recognises, so nothing was written.", text)
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])

    def test_restore_backup_refuses_another_backup_than_the_one_shown(self):
        args = SimpleNamespace(source="backup", backup=None, expect="controller-20990101-000000.bin", force_unknown=False, write=False,
                               say=lambda t: None, hint=lambda t: None, progress=None)
        with mock.patch.object(cli, "find", lambda: [found("boot", 0x3208, 0x8C)]), mock.patch.object(cli, "open_channel", lambda i, rid: SimBoot(self.flash)), \
                mock.patch.object(recipes, "_constants", lambda a=None, b=None, c=None: (K["stock_sha256"], K["region_sha256"], K["remainder_sha256"])):
            with self.assertRaises(cli.Exit) as e:
                cli.cmd_restore(args, self.tmp)
        self.assertIn("isn't the one shown", e.exception.msg)

    def test_restore_takes_no_file_or_download_argument(self):
        for extra in (["controller-20260101-000000.bin"], ["--download"]):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                cli.main(["restore", "backup", *extra])

    def test_a_command_waits_for_no_one_while_the_app_uses_the_controller(self):
        held = state.lock_device(self.tmp)
        self.addCleanup(state.unlock_device, held)
        dev = SimBoot(self.flash)
        code, text = run(["patch", "--tweaks", "cable_360", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], dev)
        self.assertEqual(code, 2)
        self.assertIn("Another copy of the app, or the command line, is using the controller.", text)
        self.assertEqual(dev.ops, [])

    def test_no_device(self):
        code, text = run(["backup", "--store", str(self.tmp)], [])
        self.assertEqual(code, 2)
        self.assertIn("No controller found", text)


if __name__ == "__main__":
    unittest.main()
