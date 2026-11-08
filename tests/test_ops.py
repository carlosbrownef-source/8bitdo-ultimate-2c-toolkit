# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from u2c_customfw import cli, transport
from u2c_customfw.firmware import image, recipes
from u2c_customfw.ops import backup as bkp, devices, patch, plan, probe, report, restore
from u2c_customfw.ops.plan import OpError
from u2c_customfw.sim import SimApp, SimBoot

rnd = random.Random(11)
STOCK = hashlib.sha256  # alias for brevity


def make_stock():
    """A synthetic 'stock' bank A with matching constants (see tests/test_firmware.py), installed into recipes."""
    s = bytearray(rnd.randbytes(image.BANK_A_SIZE))
    s[0x18274 - image.BASE:] = bytes(image.BANK_A_END - 0x18274)
    return bytes(s)


STOCK_A = make_stock()
WHOLE = recipes.whole(STOCK_A)
K = dict(stock_sha256=hashlib.sha256(STOCK_A).hexdigest(),
         region_sha256={(e.addr, e.size): hashlib.sha256(WHOLE[e.addr - image.BASE:e.addr - image.BASE + e.size]).hexdigest()
                        for r in recipes.RECIPES.values() for e in r.edits},
         remainder_sha256=hashlib.sha256(recipes.masked(WHOLE)).hexdigest())


def controller_flash(bank_a=STOCK_A):
    f = bytearray(b"\xff" * image.FLASH_SIZE)
    f[0:0x5000] = rnd.randbytes(0x5000)
    f[image.BASE:image.BASE + len(bank_a)] = bank_a
    f[0x40000:0x40000 + image.BANK_A_SIZE] = bank_a[:image.BANK_A_SIZE]
    f[0x3F000:0x3F034] = rnd.randbytes(0x34)
    f[0x3F00C] = 0x6D  # update record: firmware version 1.09
    f[0x3F018:0x3F01C] = bytes(4)  # no pending update
    f[0x3F020:0x3F024] = bytes(4)
    for a in range(image.CONFIG_START, image.FLASH_SIZE, 0x1000):
        f[a:a + 64] = rnd.randbytes(64)
    return bytes(f)


def noprogress(*a):
    pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.object(recipes, "_constants", lambda a=None, b=None, c=None: (K["stock_sha256"], K["region_sha256"], K["remainder_sha256"]))
        p.start()
        self.addCleanup(p.stop)

    def backup_of(self, flash):
        return bkp.backup(SimApp(flash), "cable", self.tmp, noprogress)


class BackupTest(Base):
    def test_backup_saves_a_checked_file_and_identifies_stock(self):
        f = controller_flash()
        b = self.backup_of(f)
        self.assertEqual(b.path.read_bytes(), f)
        self.assertEqual(b.sha256, hashlib.sha256(f).hexdigest())
        self.assertEqual((b.state.known, b.state.recipes), (True, ()))
        self.assertIn(b.sha256, (self.tmp / "SHA256SUMS").read_text())

    def test_dongle_refused(self):
        f = bytearray(controller_flash()); f[0x10000:0x10010] = b"\xff" * 16
        with self.assertRaises(OpError) as e:
            bkp.backup(SimApp(bytes(f)), "cable", self.tmp, noprogress)
        self.assertIn("dongle", str(e.exception))

    def test_passes_that_differ_are_refused(self):
        dev = SimApp(controller_flash())
        real, calls = dev.xfer, [0]

        def flaky(req, timeout=0.5):
            r = real(req, timeout)
            calls[0] += 1
            if calls[0] > 11000 and r and req[2] == 0x05:
                r = bytearray(r); r[18] ^= 1; r = bytes(r)
            return r
        dev.xfer = flaky
        with self.assertRaises(OpError) as e:
            bkp.backup(dev, "cable", self.tmp, noprogress)
        self.assertIn("differ", str(e.exception))
        self.assertEqual(list(self.tmp.glob("controller-*.bin")), [])

    def test_find_backups_matches_the_unit(self):
        f = controller_flash()
        b = self.backup_of(f)
        self.assertEqual([x.path for x in bkp.find_backups(self.tmp, f[:0x6000], f[image.MAC_SECTOR:image.MAC_SECTOR + 0x1000])], [b.path])
        other = bytearray(f[image.MAC_SECTOR:image.MAC_SECTOR + 0x1000]); other[3] ^= 1
        self.assertEqual(bkp.find_backups(self.tmp, f[:0x6000], bytes(other)), [])


class SameUnitTest(Base):
    """Pairing again adds one to the address at the start of the sector, so a controller's older backups must still count."""

    def moved(self, flash, by):
        f = bytearray(flash)
        n = int.from_bytes(f[image.MAC_SECTOR:image.MAC_SECTOR + 3], "little") + by
        f[image.MAC_SECTOR:image.MAC_SECTOR + 3] = (n % 0x1000000).to_bytes(3, "little")
        return bytes(f)

    def test_a_backup_from_before_pairing_again_still_works(self):
        f = controller_flash()
        b = self.backup_of(f)
        dev = SimBoot(self.moved(f, 2))
        self.assertTrue(patch.plan_patch(dev, b, STOCK_A, ["cable_360"]).bank_a)
        restore.plan_restore(dev, b, "backup", None)

    def test_the_new_address_can_carry_into_the_next_byte(self):
        f = bytearray(controller_flash()); f[image.MAC_SECTOR:image.MAC_SECTOR + 3] = b"\xff\x10\x20"
        now = self.moved(bytes(f), 2)
        self.assertEqual(now[image.MAC_SECTOR:image.MAC_SECTOR + 3], b"\x01\x11\x20")
        self.assertTrue(image.same_unit(bytes(f[image.MAC_SECTOR:image.MAC_SECTOR + 16]), now[image.MAC_SECTOR:image.MAC_SECTOR + 16]))

    def test_find_backups_finds_it_after_pairing_again(self):
        f = controller_flash()
        b = self.backup_of(f)
        now = self.moved(f, 2)
        self.assertEqual([x.path for x in bkp.find_backups(self.tmp, f[:0x6000], now[image.MAC_SECTOR:image.MAC_SECTOR + 0x1000])], [b.path])

    def test_the_pairing_flag_doesnt_matter(self):
        f = bytearray(controller_flash())
        a = bytes(f[image.MAC_SECTOR:image.MAC_SECTOR + 0x1000])
        f[image.MAC_SECTOR + 6] ^= 1
        self.assertTrue(image.same_unit(a, bytes(f[image.MAC_SECTOR:image.MAC_SECTOR + 0x1000])))

    def test_a_distant_address_is_another_controller(self):
        f = controller_flash()
        b = self.backup_of(f)
        with self.assertRaises(OpError) as e:
            patch.plan_patch(SimBoot(self.moved(f, 0x10000)), b, STOCK_A, ["cable_360"])
        self.assertIn("another controller", str(e.exception))


class OriginalFirmwareTest(Base):
    """Installing from "your backup" needs the original firmware, which the newest backup's bank A may no longer hold."""
    args = SimpleNamespace(download=False)

    def test_bank_b_holds_it_when_bank_a_has_tweaks(self):
        f = bytearray(controller_flash(recipes.build(STOCK_A, ["cable_360"])))
        f[0x40000:0x40000 + image.BANK_A_SIZE] = STOCK_A
        self.assertEqual(cli.stock_for(self.args, self.backup_of(bytes(f)), self.tmp), STOCK_A)

    def test_an_older_backup_holds_it(self):
        self.backup_of(controller_flash())
        newest = self.backup_of(controller_flash(recipes.build(STOCK_A, ["cable_360"])))
        self.assertEqual(cli.stock_for(self.args, newest, self.tmp), STOCK_A)

    def test_no_backup_holds_it(self):
        newest = self.backup_of(controller_flash(recipes.build(STOCK_A, ["cable_360"])))
        with self.assertRaises(cli.Exit) as e:
            cli.stock_for(self.args, newest, self.tmp)
        self.assertIn("8BitDo", str(e.exception))


class TailTest(Base):
    """Code past the payload: 0x18400-0x19000, erased with bank A."""

    def setUp(self):
        super().setUp()
        self.flash = controller_flash()
        self.backup = self.backup_of(self.flash)

    def test_an_edit_past_the_payload_is_written_and_read_back(self):
        dev = SimBoot(self.flash)
        patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, ["ring_5"]), noprogress)
        want = recipes.build(STOCK_A, ["ring_5"])
        self.assertEqual(bytes(dev.f[image.BASE:image.APP_END]), want)
        self.assertNotEqual(bytes(dev.f[0x18400:0x18404]), b"\xff" * 4)

    def test_writing_in_the_tail_doesnt_touch_the_next_sector(self):
        dev = SimBoot(self.flash)
        patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, ["ring_5"]), noprogress)
        self.assertEqual(bytes(dev.f[image.APP_END:]), self.flash[image.APP_END:])

    def test_the_payload_keeps_the_proven_stream(self):
        dev = SimBoot(self.flash)
        patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, ["ring_5"]), noprogress)
        writes = [o for o in dev.ops if o[0] == "write"]
        self.assertEqual(writes[0][1], image.BASE)
        addrs = [o[1] for o in writes]
        self.assertEqual(addrs[:image.BANK_A_SIZE // 46 + 1], list(range(image.BASE, image.BANK_A_END, 46)))

    def test_a_blank_tail_isnt_written(self):
        dev = SimBoot(self.flash)
        patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, ["dim_leds"]), noprogress)
        self.assertLess(max(o[1] for o in dev.ops if o[0] == "write"), image.BANK_A_END)

    def test_firmware_with_code_past_the_payload_can_be_patched(self):
        dev = SimBoot(self.flash)
        patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, ["ring_5"]), noprogress)
        self.assertEqual(probe.read_firmware(dev, "boot").state.recipes, ("ring_5",))
        patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, ["dim_leds"]), noprogress)
        self.assertEqual(probe.read_firmware(dev, "boot").state.recipes, ("dim_leds",))
        self.assertEqual(bytes(dev.f[image.BANK_A_END:image.APP_END]), b"\xff" * (image.APP_END - image.BANK_A_END))

    def test_restoring_the_original_blanks_the_tail(self):
        dev = SimBoot(self.flash)
        patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, ["ring_5"]), noprogress)
        patch.apply(dev, restore.plan_restore(dev, self.backup, "stock", STOCK_A), noprogress)
        self.assertEqual(bytes(dev.f[image.BASE:image.APP_END]), recipes.whole(STOCK_A))

    def test_restoring_a_backup_brings_its_tail_back(self):
        dev = SimBoot(self.flash)
        patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, ["ring_5"]), noprogress)
        with_ring = bytes(dev.f[image.BASE:image.APP_END])
        later = bkp.backup(dev, "boot", self.tmp, noprogress)
        patch.apply(dev, patch.plan_patch(dev, later, STOCK_A, ["dim_leds"]), noprogress)
        patch.apply(dev, restore.plan_restore(dev, later, "backup", None), noprogress)
        self.assertEqual(bytes(dev.f[image.BASE:image.APP_END]), with_ring)


class PatchTest(Base):
    def setUp(self):
        super().setUp()
        self.flash = controller_flash()
        self.backup = self.backup_of(self.flash)

    def test_patch_writes_the_proven_stream_and_the_unit_identifies_afterwards(self):
        dev = SimBoot(self.flash)
        plan = patch.plan_patch(dev, self.backup, STOCK_A, ["bt_xbox", "bt_rumble", "cable_360", "dim_leds"])
        patch.apply(dev, plan, noprogress)
        self.assertEqual(dev.ops[0], ("erase", 0x6000, 0x19000))
        self.assertEqual([o for o in dev.ops if o[0] == "erase"].__len__(), 1)
        writes = [o for o in dev.ops if o[0] == "write"]
        self.assertEqual([w[1] for w in writes], list(range(0x6000, 0x18400, 46)))
        self.assertEqual(set(dev.params), {0x12400})
        st = recipes.identify(bytes(dev.f[0x6000:0x18400]))
        self.assertEqual(st.recipes, ("bt_rumble", "bt_xbox", "cable_360", "dim_leds"))
        self.assertEqual(bytes(dev.f[:0x6000]), self.flash[:0x6000])
        self.assertEqual(bytes(dev.f[0x19000:]), self.flash[0x19000:])

    def test_changing_the_ring_level_replaces_the_previous_one(self):
        dev = SimBoot(self.flash)
        for keys in (["dim_leds", "ring_25"], ["dim_leds", "ring_1"], ["dim_leds"]):
            patch.apply(dev, patch.plan_patch(dev, self.backup, STOCK_A, keys), noprogress)
            self.assertEqual(recipes.identify(bytes(dev.f[image.BASE:image.APP_END])).recipes, tuple(sorted(keys)))

    def test_a_pending_update_refuses_the_patch_and_writes_nothing(self):
        for off in (0x3F018, 0x3F020):
            f = bytearray(self.flash)
            f[off:off + 4] = (0x1234).to_bytes(4, "little")
            dev = SimBoot(bytes(f))
            with self.assertRaises(OpError) as e:
                patch.plan_patch(dev, self.backup_of(bytes(f)), STOCK_A, ["dim_leds"])
            self.assertIn("pending", str(e.exception))
            self.assertEqual(dev.ops, [])

    def test_a_blank_update_record_is_not_a_pending_update(self):
        f = bytearray(self.flash)
        f[0x3F000:0x3F034] = b"\xff" * 0x34
        dev = SimBoot(bytes(f))
        self.assertTrue(patch.plan_patch(dev, self.backup_of(bytes(f)), STOCK_A, ["dim_leds"]).bank_a)

    def test_dry_run_changes_nothing(self):
        dev = SimBoot(self.flash)
        plan = patch.plan_patch(dev, self.backup, STOCK_A, ["cable_360"])
        self.assertTrue(plan.bank_a)
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])

    def test_backup_of_another_unit_is_refused_with_no_write(self):
        other = bytearray(self.flash); other[image.MAC_SECTOR + 5] ^= 1
        dev = SimBoot(bytes(other))
        with self.assertRaises(OpError) as e:
            patch.plan_patch(dev, self.backup, STOCK_A, ["cable_360"])
        self.assertIn("another controller", str(e.exception))
        self.assertEqual(dev.ops, [])

    def test_wrong_size_backup_is_refused(self):
        short = bkp.Backup(self.backup.path, self.backup.sha256, self.backup.state, self.backup.data[:-1])
        with self.assertRaises(OpError):
            patch.plan_patch(SimBoot(self.flash), short, STOCK_A, ["cable_360"])

    def test_unknown_bank_a_is_refused_for_patching_when_the_version_is_unknown(self):
        odd = bytearray(self.flash); odd[0x9000] ^= 0xFF
        odd[0x49000] ^= 0xFF; odd[0x3F00C] = 0xFF  # bank B isn't 1.09 and the update record has no version
        dev = SimBoot(bytes(odd))
        with self.assertRaises(OpError) as e:
            patch.plan_patch(dev, self.backup, STOCK_A, ["cable_360"])
        self.assertIn("Restore", str(e.exception))

    def test_dongle_in_boot_mode_is_refused(self):
        dongle = bytearray(b"\xff" * 0x20000); dongle[:0x5000] = rnd.randbytes(0x5000)
        with self.assertRaises(OpError):
            patch.plan_patch(SimBoot(bytes(dongle)), self.backup, STOCK_A, ["cable_360"])

    def test_interrupted_write_says_what_to_do_and_a_second_run_completes(self):
        dev = SimBoot(self.flash, fail_after=40)
        plan = patch.plan_patch(dev, self.backup, STOCK_A, ["bt_xbox"])
        with self.assertRaises(OpError) as e:
            patch.apply(dev, plan, noprogress)
        self.assertIn("interrupted", str(e.exception))
        self.assertIn("Restore", str(e.exception))
        dev.fail_after = None
        patch.apply(dev, plan, noprogress)
        self.assertEqual(recipes.identify(bytes(dev.f[0x6000:0x18400])).recipes, ("bt_xbox",))

    def test_writes_outside_the_allowed_range_are_refused(self):
        dev = SimBoot(self.flash)
        plan = patch.plan_patch(dev, self.backup, STOCK_A, ["cable_360"])
        for bad in (0x4000, 0x73000, 0x76000):
            with self.assertRaises(OpError):
                patch.apply(dev, patch.Plan(plan.image, True, [bad], 1, "x"), noprogress)
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])


class RestoreTest(Base):
    def setUp(self):
        super().setUp()
        self.flash = controller_flash()
        self.backup = self.backup_of(self.flash)

    def damaged(self):
        d = bytearray(self.flash)
        d[0x6000:0x18400] = rnd.randbytes(0x12400)
        d[0x45000] ^= 0xFF
        d[0x3F004] ^= 0xFF
        return SimBoot(bytes(d))

    def test_restore_from_backup_returns_the_flash_byte_for_byte(self):
        dev = self.damaged()
        plan = restore.plan_restore(dev, self.backup, "backup", None)
        patch.apply(dev, plan, noprogress)
        self.assertEqual(bytes(dev.f[:image.CONFIG_START]), self.flash[:image.CONFIG_START])

    def test_restore_accepts_an_unknown_bank_a(self):
        dev = self.damaged()
        self.assertTrue(restore.plan_restore(dev, self.backup, "backup", None).bank_a)

    def test_restore_stock_writes_only_bank_a(self):
        dev = self.damaged()
        before = bytes(dev.f)
        plan = restore.plan_restore(dev, self.backup, "stock", STOCK_A)
        patch.apply(dev, plan, noprogress)
        self.assertEqual(bytes(dev.f[0x6000:0x18400]), STOCK_A)
        self.assertEqual(bytes(dev.f[0x19000:]), before[0x19000:])

    def test_restore_checks_the_unit(self):
        other = bytearray(self.flash); other[image.MAC_SECTOR + 9] ^= 1
        with self.assertRaises(OpError):
            restore.plan_restore(SimBoot(bytes(other)), self.backup, "backup", None)


class ReportTest(Base):
    def test_report_contains_no_unit_secrets(self):
        f = controller_flash()
        mac, bonds = f[image.MAC_SECTOR:image.MAC_SECTOR + 16], f[0x7C000:0x7C010]
        found = [devices.Found(transport.DeviceInfo(0x2DC8, 0x310A, 0xFF7A, "USB", "8BitDo Ultimate 2C", None), "cable")]
        text = report.report(found, self.backup_of(f).state, "last log line")
        self.assertIn("cable", text)
        self.assertIn("last log line", text)
        for secret in (mac, bonds):
            self.assertNotIn(secret.hex(), text)


class WordingTest(unittest.TestCase):
    def test_one_byte_and_one_block_are_singular(self):
        self.assertEqual(plan.count(1, "byte"), "1 byte")
        self.assertEqual(plan.count(2, "byte"), "2 bytes")
        self.assertEqual(plan.count(0, "other 4 KB block"), "0 other 4 KB blocks")

    def test_messages_are_full_sentences(self):
        sources = Path(recipes.__file__).parent.parent
        for path in sources.rglob("*.py"):
            text = path.read_text()
            for telegraphic in ("; nothing written", "; nothing was saved", "(dry run):", "refusing to", "Not accepted yet"):
                self.assertNotIn(telegraphic, text, path.name)


class UnknownFirmwareMessageTest(Base):
    def test_patch_refusal_explains_the_two_likely_causes(self):
        f = bytearray(controller_flash())
        f[0x6000:0x6010] = bytes(16)
        f[0x40000:0x40010] = bytes(16)  # bank B isn't 1.09 either
        f[0x3F00C] = 0xFF               # and the update record has no version
        f = bytes(f)
        with self.assertRaises(OpError) as e:
            patch.plan_patch(SimBoot(f), self.backup_of(f), STOCK_A, ["dim_leds"])
        for part in ("another firmware version", "8BitDo's own updater", "modified outside this app", "Restore", "nothing was written"):
            self.assertIn(part, str(e.exception))


class DiagnosticsDataTest(Base):
    def record(self, off, value):
        f = bytearray(controller_flash())
        f[off:off + 4] = value
        return bytes(f)

    def test_pending_update_reads_both_fields(self):
        for dev, mode in ((SimBoot, "boot"), (SimApp, "cable")):
            self.assertFalse(probe.pending_update(dev(controller_flash()), mode))
            self.assertTrue(probe.pending_update(dev(self.record(0x3F018, b"\x01\0\0\0")), mode))
            self.assertTrue(probe.pending_update(dev(self.record(0x3F020, b"\x01\0\0\0")), mode))
            self.assertFalse(probe.pending_update(dev(self.record(0x3F018, b"\xff" * 4)), mode))

    def test_firmware_reports_identity_in_update_mode(self):
        self.assertEqual(probe.read_firmware(SimBoot(controller_flash()), "boot").boot_identity, 0x301B)
        self.assertIsNone(probe.read_firmware(SimApp(controller_flash()), "cable").boot_identity)

    def test_firmware_reports_a_pending_update(self):
        self.assertFalse(probe.read_firmware(SimBoot(controller_flash()), "boot").pending)
        self.assertTrue(probe.read_firmware(SimBoot(self.record(0x3F020, b"\x01\0\0\0")), "boot").pending)

    def test_firmware_asks_the_identity_once_in_update_mode(self):
        class Counting(SimBoot):
            asked = 0

            def xfer(self, r, timeout=0.5):
                self.asked += int.from_bytes(r[1:3], "little") == 8
                return super().xfer(r, timeout)
        for identity in ("auto", None):
            ch = Counting(controller_flash(), identity=identity)
            probe.read_firmware(ch, "boot")
            self.assertEqual(ch.asked, 1, identity)

    def test_firmware_identity_unanswered(self):
        fw = probe.read_firmware(SimBoot(controller_flash(), identity=None), "boot")
        self.assertIsNone(fw.boot_identity)
        self.assertTrue(fw.state.known)

    def test_refusal_says_where_install_anyway_is(self):
        f = bytearray(controller_flash())
        f[0x3F00C] = 0xFF
        f[0x6000:0x18400] = bytes(image.BANK_A_SIZE)
        f[0x40000:0x40000 + image.BANK_A_SIZE] = bytes(image.BANK_A_SIZE)
        f = bytes(f)
        with self.assertRaises(OpError) as e:
            restore.plan_restore(SimBoot(f), self.backup_like(f), "stock", STOCK_A)
        self.assertIn("in the Diagnostics tab", str(e.exception))

    def backup_like(self, f):
        return self.backup_of(f)

    def test_report_includes_extras(self):
        extras = report.clean_extras({"macos": {"name": "8BitDo Ultimate 2C (X/S)", "category": "Xbox One", "localities": ["default", "left"]},
                                      "boot_identity": 0x301B, "pending": False})
        text = report.report([], None, "", extras)
        for want in ("8BitDo Ultimate 2C (X/S)", "Xbox One", "default, left", "0x301b", "Pending update: no"):
            self.assertIn(want, text)

    def test_report_uses_the_firmware_the_page_read(self):
        text = report.report([], None, "", report.clean_extras({"firmware": "1.09 with 2 tweaks"}))
        self.assertIn("Firmware: 1.09 with 2 tweaks", text)
        self.assertNotIn("not read", text)
        self.assertEqual(len(report.clean_extras({"firmware": "x" * 999})["firmware"]), 120)
        self.assertEqual(report.clean_extras({"firmware": 5}), {})

    def test_report_uses_the_apps_name(self):
        self.assertTrue(report.report([], None, "").startswith("Firmware Toolkit "))

    def test_report_without_extras_is_unchanged(self):
        self.assertEqual(report.report([], None, "x"), report.report([], None, "x", {}))
        self.assertNotIn("macOS sees", report.report([], None, "x"))

    def test_report_ignores_bad_extras(self):
        for bad in ("x", [], None, 5, {"macos": 5}, {"macos": "x"}, {"boot_identity": "x"}, {"boot_identity": True}, {"pending": "yes"}):
            self.assertEqual(report.clean_extras(bad), {}, bad)
        kept = report.clean_extras({"macos": {"name": "n" * 5000, "category": 7, "localities": ["a" * 99] + [1] + ["b"] * 20}})
        self.assertEqual(len(kept["macos"]["name"]), 80)
        self.assertNotIn("category", kept["macos"])
        self.assertEqual(len(kept["macos"]["localities"]), 8)
        self.assertEqual(len(kept["macos"]["localities"][0]), 40)
        self.assertNotIn(1, kept["macos"]["localities"])

    def test_report_keeps_only_the_known_fields(self):
        kept = report.clean_extras({"mac": "aa:bb", "macos": {"name": "n", "address": "aa:bb"}})
        self.assertEqual(kept, {"macos": {"name": "n"}})


class ProbeTest(Base):
    def test_cable_stock_and_patched(self):
        self.assertEqual(probe.read_state(SimApp(controller_flash()), "cable"), recipes.State(True, ()))
        built = recipes.build(STOCK_A, ["bt_xbox", "dim_leds"], **K)
        st = probe.read_state(SimApp(controller_flash(built)), "cable_360")
        self.assertEqual((st.known, st.recipes), (True, ("bt_xbox", "dim_leds")))

    def test_boot_mode_and_unknown(self):
        odd = bytearray(controller_flash()); odd[0x9000] ^= 0xFF
        self.assertFalse(probe.read_state(SimBoot(bytes(odd)), "boot").known)

    def test_dongle_refused(self):
        f = bytearray(controller_flash()); f[0x10000:0x10010] = b"\xff" * 16
        with self.assertRaises(OpError):
            probe.read_state(SimApp(bytes(f)), "cable")


class VersionTest(Base):
    def setUp(self):
        super().setUp()
        self.flash = controller_flash()
        self.backup = bkp.backup(SimApp(self.flash), "cable", self.tmp, noprogress)

    def device(self, record=0x6D, bank_a=None, bank_b=None, boot_mode=False):
        f = bytearray(self.flash)
        f[0x3F00C] = record
        if bank_a is not None:
            f[0x6000:0x18400] = bank_a
        if bank_b is not None:
            f[0x40000:0x52400] = bank_b
        return SimBoot(bytes(f)) if boot_mode else SimApp(bytes(f))

    def test_version_comes_from_the_update_record(self):
        self.assertEqual(probe.detect_version(self.device(106), "cable"), (1.06, "update record"))
        self.assertEqual(probe.detect_version(self.device(0x6D, boot_mode=True), "boot"), (1.09, "update record"))

    def test_blank_record_falls_back_to_the_hash_of_bank_a_then_bank_b(self):
        odd = bytes(random.Random(5).randbytes(0x12400))
        for blank in (0xFF, 0x00):
            self.assertEqual(probe.detect_version(self.device(blank), "cable"), (1.09, "bank A hash"))
            self.assertEqual(probe.detect_version(self.device(blank, bank_a=odd), "cable"), (1.09, "bank B hash"))
            self.assertEqual(probe.detect_version(self.device(blank, bank_a=odd, bank_b=odd), "cable"), (None, "unknown"))

    def test_stock_restore_refused_on_another_firmware_version(self):
        dev = self.device(106, boot_mode=True)
        with self.assertRaises(OpError) as e:
            restore.plan_restore(dev, self.backup, "stock", STOCK_A)
        self.assertIn("1.06", str(e.exception))
        self.assertIn("1.09", str(e.exception))

    def test_stock_restore_refused_when_the_version_cannot_be_determined(self):
        odd = bytes(random.Random(6).randbytes(0x12400))
        dev = self.device(0xFF, bank_a=odd, bank_b=odd, boot_mode=True)
        with self.assertRaises(OpError) as e:
            restore.plan_restore(dev, self.backup, "stock", STOCK_A)
        self.assertIn("can't be identified", str(e.exception))

    def test_patch_replaces_unrecognised_firmware_when_the_controller_has_1_09(self):
        odd = bytes(random.Random(9).randbytes(0x12400))
        for dev in (self.device(0x6D, bank_a=odd, boot_mode=True), self.device(0xFF, bank_a=odd, boot_mode=True)):
            plan = patch.plan_patch(dev, self.backup, STOCK_A, ["dim_leds"])
            self.assertIn("doesn't recognise", plan.summary)
            patch.apply(dev, plan, noprogress)
            self.assertEqual(recipes.identify(bytes(dev.f[image.BASE:image.APP_END])).recipes, ("dim_leds",))

    def test_patch_refused_over_unrecognised_firmware_of_another_version(self):
        dev = self.device(106, bank_a=bytes(random.Random(10).randbytes(0x12400)), boot_mode=True)
        with self.assertRaises(OpError) as e:
            patch.plan_patch(dev, self.backup, STOCK_A, ["dim_leds"])
        self.assertIn("1.06", str(e.exception))
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])

    def test_patch_refused_when_unrecognised_and_the_version_cannot_be_determined(self):
        odd = bytes(random.Random(11).randbytes(0x12400))
        dev = self.device(0xFF, bank_a=odd, bank_b=odd, boot_mode=True)
        with self.assertRaises(OpError) as e:
            patch.plan_patch(dev, self.backup, STOCK_A, ["dim_leds"])
        self.assertIn("nothing was written", str(e.exception))
        self.assertEqual([o for o in dev.ops if o[0] != "read"], [])

    def test_force_install_only_overrides_an_unknown_version(self):
        odd = bytes(random.Random(8).randbytes(0x12400))
        unknown = self.device(0xFF, bank_a=odd, bank_b=odd, boot_mode=True)
        with self.assertRaises(OpError):
            restore.plan_restore(unknown, self.backup, "stock", STOCK_A)
        plan = restore.plan_restore(unknown, self.backup, "stock", STOCK_A, force_unknown=True)
        self.assertTrue(plan.bank_a)
        # a version that is known and different is never overridden: that is 8BitDo's updater's job
        with self.assertRaises(OpError) as e:
            restore.plan_restore(self.device(106, boot_mode=True), self.backup, "stock", STOCK_A, force_unknown=True)
        self.assertIn("1.06", str(e.exception))

    def test_force_install_still_checks_the_unit_and_the_device_kind(self):
        odd = bytes(random.Random(9).randbytes(0x12400))
        other = bytearray(self.flash); other[image.MAC_SECTOR + 3] ^= 1
        dev = SimBoot(bytes(other)); dev.f[0x3F00C] = 0xFF; dev.f[0x6000:0x18400] = odd; dev.f[0x40000:0x52400] = odd
        with self.assertRaises(OpError) as e:
            restore.plan_restore(dev, self.backup, "stock", STOCK_A, force_unknown=True)
        self.assertIn("another controller", str(e.exception))
        dongle = bytearray(b"\xff" * 0x20000); dongle[:0x5000] = random.Random(1).randbytes(0x5000)
        with self.assertRaises(OpError):
            restore.plan_restore(SimBoot(bytes(dongle)), self.backup, "stock", STOCK_A, force_unknown=True)

    def test_stock_restore_allowed_when_a_blank_record_is_resolved_by_a_bank(self):
        odd = bytes(random.Random(7).randbytes(0x12400))   # damaged bank A, blank record, bank B still stock
        dev = self.device(0xFF, bank_a=odd, boot_mode=True)
        self.assertTrue(restore.plan_restore(dev, self.backup, "stock", STOCK_A).bank_a)
        self.assertTrue(restore.plan_restore(self.device(0x6D, boot_mode=True), self.backup, "stock", STOCK_A))


class DevicesTest(unittest.TestCase):
    def test_modes(self):
        d = lambda v, p, up=0, tr="USB": transport.DeviceInfo(v, p, up, tr, "x", None)
        listing = [d(0x2DC8, 0x310A, 0xFF7A), d(0x045E, 0x028E, 0xFF7A), d(0x045E, 0x028E, 1), d(0x2DC8, 0x3208, 0x8C),
                   d(0x2DC8, 0x301C, 0xFFA0), d(0x045E, 0x0B13, 1, "Bluetooth Low Energy"), d(0x045E, 0x0B13, 1, "Bluetooth Low Energy"),
                   d(0x2DC8, 0x301B, 1, "Bluetooth Low Energy"), d(0x05AC, 0x8104, 0xFF00)]
        with mock.patch.object(transport, "list_devices", lambda: listing):
            self.assertEqual([f.mode for f in devices.find()],
                             ["cable", "cable_360", "boot", "dongle", "bluetooth_xbox", "bluetooth"])


    def test_two_devices_of_the_same_mode_are_both_listed(self):
        d = lambda h: transport.DeviceInfo(0x2DC8, 0x3208, 0x8C, "USB", "x", h)
        with mock.patch.object(transport, "list_devices", lambda: [d("a"), d("b")]):
            self.assertEqual([f.info.handle for f in devices.find()], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
