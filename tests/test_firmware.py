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
RING = {"ring_off": 0, "ring_0_1": 1, "ring_1": 10, "ring_5": 50, "ring_25": 250}  # PWM compare value, period 1000
RING_LEVEL_ADDR = 0x76D0


def synthetic():
    """A random 'stock' bank A, with the recipes' stock hashes and the remainder hash recomputed for it."""
    rnd = random.Random(4)
    stock = bytearray(rnd.randbytes(image.BANK_A_SIZE))
    stock[0x18274 - image.BASE:] = bytes(image.BANK_A_END - 0x18274)  # the zero tail, as in the real image
    stock = bytes(stock)
    whole = recipes.whole(stock)
    region_sha = {(e.addr, e.size): hashlib.sha256(whole[e.addr - image.BASE:e.addr - image.BASE + e.size]).hexdigest()
                  for r in recipes.RECIPES.values() for e in r.edits}
    return stock, dict(stock_sha256=hashlib.sha256(stock).hexdigest(), region_sha256=region_sha,
                       remainder_sha256=hashlib.sha256(recipes.masked(whole)).hexdigest())


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

    def test_edits_stay_inside_the_app_area(self):
        for r in recipes.RECIPES.values():
            for e in r.edits:
                self.assertGreaterEqual(e.addr, image.BASE)
                self.assertLessEqual(e.addr + e.size, image.APP_END)

    def test_stock_identifies_as_stock(self):
        st = recipes.identify(self.stock, **self.k)
        self.assertEqual((st.known, st.recipes), (True, ()))


class ControllerNameTest(unittest.TestCase):
    NEW, OLD = b"8BitDo Ultimate 2C (X/S)", b"8BitDo Ultimate 2C (One)"
    GATT, SCAN = 0x172DC - image.BASE, 0x17254 - image.BASE + 2

    def setUp(self):
        self.stock, self.k = synthetic()
        self.built = recipes.build(self.stock, ["bt_xbox"], **self.k)

    def with_old_name(self, img, *at):
        out = bytearray(img)
        for a in at:
            out[a:a + len(self.OLD)] = self.OLD
        return bytes(out)

    def test_new_installs_use_the_new_name(self):
        self.assertEqual(self.built[self.GATT:self.GATT + len(self.NEW)], self.NEW)
        self.assertEqual(self.built[self.SCAN:self.SCAN + len(self.NEW)], self.NEW)

    def test_a_controller_with_the_old_name_is_still_recognised(self):
        st = recipes.identify(self.with_old_name(self.built, self.GATT, self.SCAN), **self.k)
        self.assertEqual((st.known, st.recipes), (True, ("bt_xbox",)))

    def test_any_other_name_is_unknown(self):
        bad = bytearray(self.built)
        bad[self.GATT:self.GATT + 3] = b"XXX"
        self.assertFalse(recipes.identify(bytes(bad), **self.k).known)

    def test_every_combination_installed_with_the_old_name_is_still_recognised(self):
        for keys in VALID + [k + [r] for k in VALID for r in RING]:
            if "bt_xbox" not in keys:
                continue
            st = recipes.identify(self.with_old_name(recipes.build(self.stock, keys, **self.k), self.GATT, self.SCAN), **self.k)
            self.assertEqual((st.known, st.recipes), (True, tuple(sorted(keys))), keys)

    def test_the_published_tweaks_keep_their_bytes(self):
        """Firmware installed by 0.1.x and 0.2.0 is only recognised while these match: changing a blob needs an `accepts` for the old one."""
        published = {
        "packer.bin": "1ba223dee721be22c4a64575784013bedebb0e5706b5bd4a93cd760b985424e9",
        "noop.bin": "7817034cdd42530d23894be6e9dd41a777ec2a407cc73c69ac0665fc047e4d1e",
        "rumble02.bin": "7948fb82193d6e9f033d83fe4efe015adebc5fe33b3570b6aff6344f11ae0426",
        "led.bin": "7876889cb9c2981ee4e78338f2eca0589f431d509f361f6b5d029f5eeb7eecd1",
        "hook.bin": "012f37b995249381906e85cb32b127cfebd08f92ed34253b1d93ffe690b8a28e",
        "report-map.bin": "a681e2cb8b5d9466f258e2f07f0fcc518ec438231af1b61b125c213d2c62e165",
        "ring02.bin": "3230e6f5f644389a1cf7de4d8d12f7c0c5994b1d3fefa3156e1658b708336b35",
        "ringhook02.bin": "36bb496143d7a87026b50fe0220ef246c168c3b6b6251f4286b33edf1498222d",
        }
        for name, sha in published.items():
            self.assertEqual(hashlib.sha256((recipes.BLOBS / name).read_bytes()).hexdigest(), sha, name)
        self.assertEqual(recipes.NAME, b"8BitDo Ultimate 2C (X/S)")
        self.assertEqual([level for _, _, level in recipes.RING_LEVELS], [0, 1, 10, 50, 250, 0xFFFF])

    def test_the_old_name_alone_does_not_count_as_the_tweak(self):
        bad = bytearray(self.stock)
        bad[self.GATT:self.GATT + len(self.OLD)] = self.OLD
        self.assertFalse(recipes.identify(bytes(bad), **self.k).known)


class PastThePayloadTest(unittest.TestCase):
    def setUp(self):
        self.stock, self.k = synthetic()

    def test_stock_is_recognised_with_a_blank_tail(self):
        for img in (self.stock, recipes.whole(self.stock)):
            st = recipes.identify(img, **self.k)
            self.assertEqual((st.known, st.recipes), (True, ()))

    def test_a_non_blank_tail_with_no_recipe_is_unknown(self):
        bad = bytearray(recipes.whole(self.stock))
        bad[image.APP_END - image.BASE - 1] = 0
        self.assertFalse(recipes.identify(bytes(bad), **self.k).known)

    def test_build_covers_the_whole_app_area(self):
        self.assertEqual(len(recipes.build(self.stock, ["dim_leds"], **self.k)), image.APP_SIZE)

    def test_a_tweak_without_code_past_the_payload_leaves_it_blank(self):
        img = recipes.build(self.stock, ["dim_leds"], **self.k)
        self.assertEqual(img[image.BANK_A_SIZE:], b"\xff" * (image.APP_SIZE - image.BANK_A_SIZE))

    def test_the_ring_code_is_past_the_payload(self):
        img = recipes.build(self.stock, ["ring_5"], **self.k)
        self.assertNotEqual(img[0x18400 - image.BASE:0x18404 - image.BASE], b"\xff" * 4)


class FromEarlierVersionsTest(unittest.TestCase):
    """Firmware installed by 0.2.0 must stay recognised, with its level."""

    def setUp(self):
        self.stock, self.k = synthetic()

    def from_0_2(self, tweaks, level):
        img = bytearray(recipes.build(self.stock, tweaks, **self.k))
        rumble = (recipes.BLOBS / "rumble02.bin").read_bytes()
        if "bt_rumble" in tweaks:
            img[0x18390 - image.BASE:0x18400 - image.BASE] = rumble.ljust(0x70, b"\0")
        img[0xA3FA - image.BASE] = 0
        hook = (recipes.BLOBS / "ringhook02.bin").read_bytes()
        img[0xD4F0 - image.BASE:0xD4F4 - image.BASE] = hook
        img[0x7640 - image.BASE:0x76D0 - image.BASE] = (recipes.BLOBS / "ring02.bin").read_bytes().ljust(0x90, b"\0")
        img[RING_LEVEL_ADDR - image.BASE:RING_LEVEL_ADDR - image.BASE + 2] = level.to_bytes(2, "little")
        return bytes(img)

    def test_firmware_from_0_2_is_still_recognised(self):
        for ring, value in RING.items():
            for keys in ([], ["dim_leds"], KEYS):
                st = recipes.identify(self.from_0_2(keys, value), **self.k)
                self.assertEqual((st.known, st.recipes), (True, tuple(sorted(keys + [ring]))), ring)
                self.assertTrue(st.outdated, ring)

    def test_current_firmware_is_not_outdated(self):
        self.assertFalse(recipes.identify(recipes.build(self.stock, ["ring_5"], **self.k), **self.k).outdated)

    def test_earlier_versions_cant_be_installed(self):
        with self.assertRaises(RecipeError):
            recipes.build(self.stock, ["ring_5@0.2"], **self.k)

    def test_the_new_hook_without_its_code_is_unknown(self):
        bad = bytearray(recipes.build(self.stock, ["ring_5"], **self.k))
        bad[0x18400 - image.BASE:0x18FF0 - image.BASE] = b"\xff" * (0x18FF0 - 0x18400)
        self.assertFalse(recipes.identify(bytes(bad), **self.k).known)


class BatteryAlertsTest(unittest.TestCase):
    def setUp(self):
        self.stock, self.k = synthetic()

    def test_alerts_need_a_ring_level(self):
        with self.assertRaises(RecipeError):
            recipes.build(self.stock, ["battery_alerts"], **self.k)

    def test_alerts_identify_with_each_level(self):
        for ring in [*RING, "ring_normal"]:
            st = recipes.identify(recipes.build(self.stock, [ring, "battery_alerts"], **self.k), **self.k)
            self.assertEqual((st.known, st.recipes), (True, tuple(sorted([ring, "battery_alerts"]))), ring)

    def test_alerts_without_the_ring_are_unknown(self):
        img = bytearray(recipes.whole(self.stock))
        img[0x18FF0 - image.BASE] = 1
        self.assertFalse(recipes.identify(bytes(img), **self.k).known)


class RingTest(unittest.TestCase):
    def setUp(self):
        self.stock, self.k = synthetic()

    def test_each_level_identifies_alone_and_with_the_other_tweaks(self):
        for ring in RING:
            for keys in ([], ["dim_leds"], KEYS):
                st = recipes.identify(recipes.build(self.stock, keys + [ring], **self.k), **self.k)
                self.assertTrue(st.known, ring)
                self.assertEqual(st.recipes, tuple(sorted(keys + [ring])))

    def test_each_level_stores_its_pwm_value(self):
        for ring, value in RING.items():
            img = recipes.build(self.stock, [ring], **self.k)
            self.assertEqual(int.from_bytes(img[RING_LEVEL_ADDR - image.BASE:RING_LEVEL_ADDR - image.BASE + 2], "little"), value, ring)

    def test_levels_differ_only_in_the_level_word(self):
        a, b = (recipes.build(self.stock, [k], **self.k) for k in ("ring_1", "ring_25"))
        at = RING_LEVEL_ADDR - image.BASE
        self.assertEqual(a[:at] + a[at + 2:], b[:at] + b[at + 2:])

    def test_two_levels_are_refused(self):
        with self.assertRaises(RecipeError) as e:
            recipes.build(self.stock, ["ring_1", "ring_5"], **self.k)
        self.assertIn("one", str(e.exception))

    def test_a_level_value_no_recipe_has_makes_the_image_unknown(self):
        bad = bytearray(recipes.build(self.stock, ["ring_1"], **self.k))
        bad[RING_LEVEL_ADDR - image.BASE] = 77
        self.assertFalse(recipes.identify(bytes(bad), **self.k).known)

    def test_a_half_installed_ring_makes_the_image_unknown(self):
        bad = bytearray(recipes.build(self.stock, ["ring_1"], **self.k))
        bad[RING_LEVEL_ADDR - image.BASE:RING_LEVEL_ADDR - image.BASE + 2] = self.stock[RING_LEVEL_ADDR - image.BASE:RING_LEVEL_ADDR - image.BASE + 2]
        self.assertFalse(recipes.identify(bytes(bad), **self.k).known)


@unittest.skipUnless(os.environ.get("U2C_STOCK_DAT"), "set U2C_STOCK_DAT to a local ultimate-2c-controller-v1.09.dat")
class RealStockTest(unittest.TestCase):
    def setUp(self):
        self.stock = Path(os.environ["U2C_STOCK_DAT"]).read_bytes()[0x1C:]

    def test_stock_identifies(self):
        st = recipes.identify(self.stock)
        self.assertEqual((st.known, st.recipes), (True, ()))

    def test_matches_the_payload_verified_on_hardware(self):
        if "U2C_REF_PAYLOAD" not in os.environ:  # a payload flashed and verified on a real controller (not in the repo)
            self.skipTest("set U2C_REF_PAYLOAD to compare with a payload verified on hardware")
        ref = Path(os.environ["U2C_REF_PAYLOAD"])
        self.assertEqual(recipes.build(self.stock, ["bt_xbox", "bt_rumble", "cable_360"]), ref.read_bytes())

    def test_all_combinations_identify(self):
        for keys in VALID + [[r] for r in RING] + [KEYS + [r] for r in RING]:
            self.assertEqual(recipes.identify(recipes.build(self.stock, keys)).recipes, tuple(sorted(keys)))


if __name__ == "__main__":
    unittest.main()
