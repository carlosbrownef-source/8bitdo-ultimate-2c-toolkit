# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import random
import unittest

from u2c_customfw.ops import dongle
from u2c_customfw.ops.plan import OpError
from u2c_customfw.sim import SimApp

rnd = random.Random(5)
STOCK = bytearray(rnd.randbytes(dongle.SIZE))
STOCK[0xF1A4 - dongle.BASE:0xF1AC - dongle.BASE] = bytes.fromhex("000000 08 c82d0a31")
STOCK = bytes(STOCK)
XBOX = bytearray(STOCK)
XBOX[0xF1A4 - dongle.BASE:0xF1AE - dongle.BASE] = bytes.fromhex("ffffff 08 5e048e02 0301")
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
