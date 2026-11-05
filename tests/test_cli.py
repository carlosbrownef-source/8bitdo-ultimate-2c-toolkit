# SPDX-License-Identifier: GPL-3.0-or-later
import contextlib
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
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
        f = bytearray(self.flash); f[image.BASE:image.BANK_A_END] = built
        p = self.tmp / "x.bin"; p.write_bytes(bytes(f))
        code, text = run(["identify", str(p)], [])
        self.assertEqual(code, 0)
        self.assertIn("bt_xbox", text)
        self.assertIn("cable_360", text)

    def test_two_devices_exit_2(self):
        code, text = run(["backup", "--store", str(self.tmp)], [found("cable"), found("dongle", 0x301C, 0xFFA0)])
        self.assertEqual(code, 2)
        self.assertIn("More than one device: unplug all but one controller.", text)

    def test_two_units_in_the_same_mode_exit_2(self):
        a = found("boot", 0x3208, 0x8C)
        code, text = run(["patch", "--tweaks", "cable_360", "--store", str(self.tmp)], [a, found("boot", 0x3208, 0x8C)], SimBoot(self.flash))
        self.assertEqual(code, 2)
        self.assertIn("More than one device", text)

    def test_protocol_errors_are_messages_not_tracebacks(self):
        class Dead(SimBoot):
            def xfer(self, r, timeout=0.5):
                return None
        code, text = run(["patch", "--tweaks", "cable_360", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], Dead(self.flash))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", text)

    def test_patch_without_write_makes_no_erase_or_write(self):
        dev = SimBoot(self.flash)
        code, text = run(["patch", "--tweaks", "cable_360", "--store", str(self.tmp)], [found("boot", 0x3208, 0x8C)], dev)
        self.assertEqual(code, 0, text)
        self.assertIn("dry run", text.lower())
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
        self.assertEqual(recipes.identify(bytes(dev.f[0x6000:0x18400]), **K).recipes, ("cable_360",))

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

    def test_no_device(self):
        code, text = run(["backup", "--store", str(self.tmp)], [])
        self.assertEqual(code, 2)
        self.assertIn("No controller found", text)


if __name__ == "__main__":
    unittest.main()
