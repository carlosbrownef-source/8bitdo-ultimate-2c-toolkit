# SPDX-License-Identifier: GPL-3.0-or-later
import ctypes as C
import gc
import sys
import unittest
from collections import Counter
from unittest import mock

from u2c_customfw import transport


class TransportTest(unittest.TestCase):
    @unittest.skipIf(sys.platform == "darwin", "macOS has a transport")
    def test_other_platforms_point_to_porting_doc(self):
        with self.assertRaises(NotImplementedError) as e:
            transport.list_devices()
        self.assertIn("docs/porting.md", str(e.exception))

    @unittest.skipUnless(sys.platform == "darwin", "IOKit only on macOS")
    def test_macos_lists_devices(self):
        devices = transport.list_devices()
        self.assertIsInstance(devices, list)
        for d in devices:
            self.assertIsInstance(d, transport.DeviceInfo)
            self.assertIsInstance(d.vendor, int)

    @unittest.skipUnless(sys.platform == "darwin", "IOKit only on macOS")
    def test_old_managers_are_released_only_with_no_channel_open(self):
        from u2c_customfw.transport import iokit
        released = []
        managers = list(range(10))
        iokit._release_old(managers, open_channels=1, keep=4, release=released.append)
        self.assertEqual((managers, released), (list(range(10)), []))
        iokit._release_old(managers, open_channels=0, keep=4, release=released.append)
        self.assertEqual((managers, released), ([6, 7, 8, 9], [0, 1, 2, 3, 4, 5]))

    @unittest.skipUnless(sys.platform == "darwin", "IOKit only on macOS")
    def test_listing_devices_releases_what_it_creates(self):
        from u2c_customfw.transport import iokit
        owed, released = Counter(), Counter()

        class Spy:
            def __init__(self, lib):
                self.lib = lib

            def __getattr__(self, name):
                real = getattr(self.lib, name)
                if name == "CFRelease":
                    return lambda p: (released.update([p]), real(p))[1]
                if name in ("CFStringCreateWithCString", "IOHIDManagerCopyDevices"):
                    def call(*args):
                        p = real(*args)
                        owed.update([p])
                        return p
                    return call
                return real

        with mock.patch.object(iokit, "cf", Spy(iokit.cf)), mock.patch.object(iokit, "iok", Spy(iokit.iok)):
            devices = iokit.list_devices()
        self.assertEqual(owed - released, Counter())
        for d in devices:  # the manager still holds them after the copy is released
            self.assertEqual(iokit._prop(d.handle, "VendorID") or 0, d.vendor)

    def fake_channel(self, late, answers=(b"answer",)):
        """A channel on fake IOKit: the run loop first delivers the replies in late, then answers once something is sent."""
        from u2c_customfw.transport import iokit
        ch = object.__new__(iokit.IOKitChannel)
        ch.dev, ch.rid, ch.replies, ch.loop, ch.buf = "dev", 0, [], "loop", None
        queue, calls = list(late), []

        def run(mode, seconds, once):
            if not queue:
                return 3   # kCFRunLoopRunTimedOut
            ch.replies.append(queue.pop(0))
            return 4       # kCFRunLoopRunHandledSource
        cf = mock.Mock(CFRunLoopRunInMode=run)
        iok = mock.Mock(IOHIDDeviceSetReport=lambda *a: queue.extend(answers) or 0,
                        IOHIDDeviceRegisterInputReportCallback=lambda *a: calls.append(a))
        for name, fake in (("cf", cf), ("iok", iok)):
            p = mock.patch.object(iokit, name, fake)
            p.start()
            self.addCleanup(p.stop)
        return ch, calls

    @unittest.skipUnless(sys.platform == "darwin", "IOKit only on macOS")
    def test_a_late_reply_isnt_taken_as_the_next_answer(self):
        ch, _ = self.fake_channel([b"late 1", b"late 2"])
        self.assertEqual(ch.xfer(b"request"), b"answer")

    @unittest.skipUnless(sys.platform == "darwin", "IOKit only on macOS")
    def test_a_late_reply_arriving_after_sending_is_passed_over_when_it_isnt_accepted(self):
        ch, _ = self.fake_channel([], answers=[b"late", b"answer"])
        self.assertEqual(ch.xfer(b"request", accept=lambda r: r == b"answer"), b"answer")
        ch, _ = self.fake_channel([], answers=[b"late"])
        self.assertIsNone(ch.xfer(b"request", 0.05, accept=lambda r: r == b"answer"))

    @unittest.skipUnless(sys.platform == "darwin", "IOKit only on macOS")
    def test_reopening_a_device_registers_nothing_python_can_free(self):
        """IOKit can't reliably remove a report callback (its set compares by context but hashes every byte), so a
        callback freed with its channel could still be called when the same device is opened again (crash: status 11)."""
        from u2c_customfw.transport import iokit
        calls = []
        iok = mock.Mock(IOHIDDeviceOpen=lambda *a: 0, IOHIDDeviceRegisterInputReportCallback=lambda *a: calls.append(a))
        with mock.patch.object(iokit, "iok", iok), mock.patch.object(iokit, "cf", mock.Mock()):
            dev = transport.DeviceInfo(vendor=0, product=0, usage_page=0, transport="USB", name="x", handle=0x1234)
            for _ in range(2):
                ch = iokit.IOKitChannel(dev, 0)
                ch.close()
                del ch
                gc.collect()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])   # the same callback, buffer and context: IOKit's set keeps one entry
        self.assertIs(calls[0][3], iokit._REPORT_CB)   # module-level, never freed

    @unittest.skipUnless(sys.platform == "darwin", "IOKit only on macOS")
    def test_reports_reach_only_the_open_channel_of_their_device(self):
        from u2c_customfw.transport import iokit
        iok = mock.Mock(IOHIDDeviceOpen=lambda *a: 0)
        with mock.patch.object(iokit, "iok", iok), mock.patch.object(iokit, "cf", mock.Mock()):
            dev = transport.DeviceInfo(vendor=0, product=0, usage_page=0, transport="USB", name="x", handle=0x1234)
            ch = iokit.IOKitChannel(dev, 0)
            report = (C.c_uint8 * 3)(1, 2, 3)
            iokit._on_report(None, 0, 0x1234, 1, 0, report, 3)
            iokit._on_report(None, 0, 0x9999, 1, 0, report, 3)   # another device
            self.assertEqual(ch.replies, [b"\x01\x02\x03"])
            ch.close()
            iokit._on_report(None, 0, 0x1234, 1, 0, report, 3)   # after closing: dropped, not delivered anywhere
            self.assertEqual(ch.replies, [b"\x01\x02\x03"])

    def test_device_info_fields(self):
        d = transport.DeviceInfo(vendor=0x2DC8, product=0x310A, usage_page=0xFF7A, transport="USB", name="x", handle=None)
        self.assertEqual((d.vendor, d.product, d.usage_page), (0x2DC8, 0x310A, 0xFF7A))


if __name__ == "__main__":
    unittest.main()
