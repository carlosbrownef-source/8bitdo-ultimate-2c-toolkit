# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from unittest import mock

from u2c_customfw import settings
from u2c_customfw.firmware import recipes
from u2c_customfw.ops import settings as ops
from u2c_customfw.ops.plan import OpError
from u2c_customfw.sim import SimApp

DEFAULTS = {f.name: f.default for f in settings.FIELDS}


def flash_with(installed=True, record=None):
    f = bytearray(b"\xff" * 0x80000)
    if installed:
        addr = settings.INSTALLED_HOOK
        hook = next(e.new for e in recipes.RECIPES["settings"].edits if e.addr == addr)
        f[addr:addr + 4] = hook
    if record:
        f[settings.SECTOR:settings.SECTOR + settings.SIZE] = record
    return bytes(f)


class RecordTest(unittest.TestCase):
    def test_defaults_match_the_firmware(self):
        self.assertEqual((DEFAULTS["dz_l"], DEFAULTS["outer_r"], DEFAULTS["vibration"], DEFAULTS["idle_min"], DEFAULTS["buzz"]), (14, 100, 100, 15, 1))
        self.assertEqual([DEFAULTS[f"remap_{i}"] for i in range(14)], list(range(14)))
        self.assertEqual(len(settings.FIELDS), 28)
        self.assertEqual([f.number for f in settings.FIELDS], list(range(28)))

    def test_round_trip(self):
        values = dict(DEFAULTS, dz_l=7, curve_r=2, invert=5, remap_3=255, idle_min=60)
        raw = settings.encode(values)
        self.assertEqual(len(raw), settings.SIZE)
        self.assertEqual(raw[:5], b"U2CS\x01")
        self.assertEqual(settings.parse(raw), values)

    def test_crc_as_the_firmware_computes_it(self):
        # 0xaf80: init 0xffff, reflected poly 0x8408, result with its bytes swapped; CRC-16/MCRF4XX of "123456789" is 0x6F91
        self.assertEqual(settings.crc(b"123456789"), 0x916F)

    def test_parse_refuses_what_the_firmware_refuses(self):
        good = bytearray(settings.encode(DEFAULTS))
        def resealed(i, v):
            r = bytearray(good); r[i] = v
            c = settings.crc(bytes(r[:33])); r[33] = c & 0xff; r[34] = c >> 8
            return bytes(r)
        self.assertIsNone(settings.parse(b"\xff" * settings.SIZE))
        self.assertIsNone(settings.parse(bytes(good[:33]) + bytes([good[33] ^ 1, good[34]])))
        self.assertIsNone(settings.parse(resealed(4, 2)))                       # a later version
        self.assertIsNone(settings.parse(resealed(0, 0x41)))                    # the magic
        self.assertIsNone(settings.parse(resealed(5, 31)))                      # dead zone out of range
        self.assertIsNone(settings.parse(resealed(19 + 2, 14)))                 # remap to a bit that isn't a button

    def test_valid(self):
        for name, value in (("dz_l", 30), ("outer_r", 70), ("vibration", 25), ("idle_min", 5), ("remap_2", 255), ("remap_2", 13)):
            self.assertTrue(settings.valid(name, value), (name, value))
        for name, value in (("dz_l", 31), ("dz_l", -1), ("dz_l", True), ("dz_l", "5"), ("dz_l", 5.0), ("outer_r", 69), ("vibration", 33),
                            ("idle_min", 7), ("buzz", 2), ("remap_2", 14), ("nothing", 1), ("curve_l", None)):
            self.assertFalse(settings.valid(name, value), (name, value))


class OpsTest(unittest.TestCase):
    def test_installed(self):
        self.assertTrue(ops.installed(SimApp(flash_with())))
        self.assertFalse(ops.installed(SimApp(flash_with(installed=False))))

    def test_read_blank_gives_defaults(self):
        got = ops.read(SimApp(flash_with()))
        self.assertEqual(got["values"], DEFAULTS)
        self.assertFalse(got["saved"])

    def test_read_saved(self):
        got = ops.read(SimApp(flash_with(record=settings.encode(dict(DEFAULTS, dz_l=7)))))
        self.assertEqual(got["values"]["dz_l"], 7)
        self.assertTrue(got["saved"])

    def test_a_change_reaches_the_controller_and_save_is_checked(self):
        ch = SimApp(flash_with())
        ops.change(ch, {"dz_l": 7})
        self.assertEqual(ch.fields[0], 7)
        self.assertTrue(ops.save(ch, dict(DEFAULTS, dz_l=7)))
        self.assertEqual(settings.parse(ch.flash[settings.SECTOR:settings.SECTOR + settings.SIZE])["dz_l"], 7)

    def test_save_says_when_the_record_differs(self):
        ch = SimApp(flash_with())
        ch.drop_saves = True
        with mock.patch.object(ops, "CONFIRM_SECONDS", 0.05):
            self.assertFalse(ops.save(ch, dict(DEFAULTS, dz_l=7)))

    def test_reset_returns_defaults(self):
        ch = SimApp(flash_with(record=settings.encode(dict(DEFAULTS, dz_l=7))))
        self.assertEqual(ops.reset(ch), DEFAULTS)
        self.assertEqual(ch.fields[0], 14)

    def test_load_brings_the_controller_back_to_what_it_kept(self):
        ch = SimApp(flash_with(record=settings.encode(dict(DEFAULTS, dz_l=7))))
        ch.fields[0] = 20
        self.assertEqual(ops.load(ch)["values"]["dz_l"], 7)
        self.assertEqual(ch.fields[0], 7)
        self.assertEqual(ch.mapping, {0: 0, 1: 0})

    def test_no_answer_is_an_error(self):
        class Gone:
            def xfer(self, *a, **k):
                return None
        with self.assertRaises(OpError):
            ops.read(Gone())


if __name__ == "__main__":
    unittest.main()
