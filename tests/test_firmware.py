# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import itertools
import os
import random
import unittest
from pathlib import Path

from u2c_customfw.firmware import image, recipes
from u2c_customfw.firmware.recipes import RecipeError

KEYS = ["bt_xbox", "bt_rumble", "cable_360", "dim_leds"]
VALID = [list(c) for n in range(5) for c in itertools.combinations(KEYS, n) if "bt_rumble" not in c or "bt_xbox" in c]


def synthetic():
    """A random 'stock' bank A, with the recipes' stock hashes and the remainder hash recomputed for it."""
    rnd = random.Random(4)
    stock = bytearray(rnd.randbytes(image.BANK_A_SIZE))
    stock[0x18274 - image.BASE:] = bytes(image.BANK_A_END - 0x18274)  # the zero tail, as in the real image
    stock = bytes(stock)
    region_sha = {(e.addr, e.size): hashlib.sha256(stock[e.addr - image.BASE:e.addr - image.BASE + e.size]).hexdigest()
                  for r in recipes.RECIPES.values() for e in r.edits}
    return stock, dict(stock_sha256=hashlib.sha256(stock).hexdigest(), region_sha256=region_sha,
                       remainder_sha256=hashlib.sha256(recipes.masked(stock)).hexdigest())


class RecipeTest(unittest.TestCase):
    def setUp(self):
        self.stock, self.k = synthetic()

    def test_every_valid_combination_builds_and_identifies(self):
        for keys in VALID:
            img = recipes.build(self.stock, keys, **self.k)
            st = recipes.identify(img, **self.k)
            self.assertTrue(st.known, keys)
            self.assertEqual(st.recipes, tuple(sorted(keys)), keys)

    def test_rumble_needs_bluetooth_identity(self):
        with self.assertRaises(RecipeError) as e:
            recipes.build(self.stock, ["bt_rumble"], **self.k)
        self.assertIn("bt_xbox", str(e.exception))

    def test_unknown_key_refused(self):
        with self.assertRaises(RecipeError):
            recipes.build(self.stock, ["turbo"], **self.k)

    def test_wrong_stock_refused(self):
        bad = bytearray(self.stock); bad[0x100] ^= 1
        with self.assertRaises(RecipeError):
            recipes.build(bytes(bad), ["cable_360"], **self.k)

    def test_one_changed_byte_makes_the_image_unknown(self):
        img = recipes.build(self.stock, ["bt_xbox", "cable_360"], **self.k)
        for addr in [e.addr for r in recipes.RECIPES.values() for e in r.edits] + [0x9000]:
            bad = bytearray(img); bad[addr - image.BASE] ^= 0x40
            self.assertFalse(recipes.identify(bytes(bad), **self.k).known, hex(addr))

    def test_edits_stay_inside_bank_a(self):
        for r in recipes.RECIPES.values():
            for e in r.edits:
                self.assertGreaterEqual(e.addr, image.BASE)
                self.assertLessEqual(e.addr + e.size, image.BANK_A_END)

    def test_stock_identifies_as_stock(self):
        st = recipes.identify(self.stock, **self.k)
        self.assertEqual((st.known, st.recipes), (True, ()))


@unittest.skipUnless(os.environ.get("U2C_STOCK_DAT"), "set U2C_STOCK_DAT to a local ultimate-2c-controller-v1.09.dat")
class RealStockTest(unittest.TestCase):
    def setUp(self):
        self.stock = Path(os.environ["U2C_STOCK_DAT"]).read_bytes()[0x1C:]

    def test_stock_identifies(self):
        st = recipes.identify(self.stock)
        self.assertEqual((st.known, st.recipes), (True, ()))

    def test_matches_the_payload_verified_on_hardware(self):
        ref = Path(os.environ.get("U2C_REF_PAYLOAD", "backups/"
                                  "payload-controller-v1.09-xbox-ble-cable360-rumble-hold.bin"))
        if not ref.exists():
            self.skipTest(f"{ref} not present")
        self.assertEqual(recipes.build(self.stock, ["bt_xbox", "bt_rumble", "cable_360"]), ref.read_bytes())

    def test_all_combinations_identify(self):
        for keys in VALID:
            self.assertEqual(recipes.identify(recipes.build(self.stock, keys)).recipes, tuple(sorted(keys)))


if __name__ == "__main__":
    unittest.main()
