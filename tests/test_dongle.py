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
