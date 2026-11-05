# SPDX-License-Identifier: GPL-3.0-or-later
import os
import unittest

from u2c_customfw.protocol import ProtocolError, app, boot
from u2c_customfw.sim import SimApp, SimBoot


def flash(size=0x80000):
    f = bytearray(b"\xff" * size)
    f[0:0x5000] = os.urandom(0x5000)
    f[0x6000:0x18400] = os.urandom(0x12400)
    return bytes(f)


class BootTest(unittest.TestCase):
    def test_crc16_modbus_check_value(self):
        self.assertEqual(boot.crc16(b"123456789"), 0x4B37)

    def test_request_matches_the_proven_encoder(self):
        # bytes produced by the hardware-tested tools/recover.py for the same arguments
        self.assertEqual(boot.request(3, 0x6000, 0x12400, b"\x01\x02")[0:19].hex(), "0503000000020081e100240100006000000102")
        self.assertEqual(boot.request(5, 0x76000, 46, datalen=46)[0:17].hex(), "05050000002e0000002e00000000600700")

    def test_read_returns_the_flash(self):
        f = flash()
        self.assertEqual(boot.read(SimBoot(f), 0x6000, 1000), f[0x6000:0x6000 + 1000])

    def test_kind(self):
        self.assertEqual(boot.kind(SimBoot(flash())), "controller")
        self.assertEqual(boot.kind(SimBoot(flash(0x20000)[:0x20000])), "dongle")

    def test_identify_query_matches_what_the_bootloader_expects(self):
        r = boot.request(8, param=4, datalen=4)
        self.assertEqual((r[0], r[1], r[5], r[9], r[13:17], r[7:9]), (5, 8, 4, 4, bytes(4), bytes(2)))

    def test_identify_reads_the_bootloader_constant(self):
        self.assertEqual(boot.identify(SimBoot(flash())), 0x301B)
        self.assertEqual(boot.identify(SimBoot(flash(), identity=0x301C)), 0x301C)

    def test_identify_without_an_answer_is_none(self):
        self.assertIsNone(boot.identify(SimBoot(flash(), identity=None)))

    def test_identify_ignores_a_reply_of_the_wrong_length(self):
        class Odd(SimBoot):
            def xfer(self, r, timeout=0.5):
                a = bytearray(super().xfer(r, timeout))
                a[6:8] = b"\x10\0"
                return bytes(a)
        self.assertIsNone(boot.identify(Odd(flash())))

    def test_kind_falls_back_to_the_flash_if_identify_is_not_answered(self):
        self.assertEqual(boot.kind(SimBoot(flash(), identity=None)), "controller")
        self.assertEqual(boot.kind(SimBoot(flash(0x20000)[:0x20000], identity=None)), "dongle")

    def test_kind_says_dongle_when_it_identifies_as_one_whatever_the_flash_looks_like(self):
        self.assertEqual(boot.kind(SimBoot(flash(), identity=0x301C)), "dongle")

    def test_kind_refuses_an_identity_it_does_not_know(self):
        self.assertIsNone(boot.kind(SimBoot(flash(), identity=0x1234)))

    def test_a_controller_identity_does_not_override_flash_that_looks_like_a_dongle(self):
        self.assertEqual(boot.kind(SimBoot(flash(0x20000)[:0x20000], identity=0x301B)), "dongle")

    def test_rejected_write_raises(self):
        dev = SimBoot(flash())

        def bad_crc(report, timeout=0.5):
            return bytes([0, 5, 1, 0, 3]).ljust(64, b"\0")
        dev.xfer = bad_crc
        with self.assertRaises(ProtocolError):
            boot.write_chunk(dev, 0x6000, 0x12400, b"\x00" * 46)


class AppTest(unittest.TestCase):
    def test_read(self):
        f = flash()
        self.assertEqual(app.read(SimApp(f), 0x10000, 46), f[0x10000:0x10000 + 46])

    def test_read_rejects_wrong_address_echo(self):
        dev = SimApp(flash())
        real = dev.xfer

        def wrong_echo(report, timeout=0.5):
            r = bytearray(real(report, timeout))
            r[14] ^= 1
            return bytes(r)
        dev.xfer = wrong_echo
        self.assertIsNone(app.read(dev, 0x10000, 16))

    def test_open_session(self):
        self.assertEqual(app.open_session(SimApp(flash())), "cold")
        dev = SimApp(flash(), needs_session=True)
        self.assertEqual(app.open_session(dev), "session")
        self.assertNotIn("81050051", [s[:8] for s in dev.sent])
        self.assertEqual(app.open_session(SimApp(flash(), needs_session=True, needs_unprotect=True)), "unprotect")


if __name__ == "__main__":
    unittest.main()
