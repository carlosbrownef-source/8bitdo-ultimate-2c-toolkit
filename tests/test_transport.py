# SPDX-License-Identifier: GPL-3.0-or-later
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

    def fake_channel(self, late):
        """A channel on fake IOKit: the run loop first delivers the replies in late, then the answer to what was sent."""
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
        iok = mock.Mock(IOHIDDeviceSetReport=lambda *a: queue.append(b"answer") or 0,
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
    def test_close_unregisters_the_report_callback(self):
        from u2c_customfw.transport import iokit
        ch, calls = self.fake_channel([])
        iokit._open_channels += 1
        ch.close()
        self.assertEqual(calls, [("dev", None, 64, None, None)])

    def test_device_info_fields(self):
        d = transport.DeviceInfo(vendor=0x2DC8, product=0x310A, usage_page=0xFF7A, transport="USB", name="x", handle=None)
        self.assertEqual((d.vendor, d.product, d.usage_page), (0x2DC8, 0x310A, 0xFF7A))


if __name__ == "__main__":
    unittest.main()
