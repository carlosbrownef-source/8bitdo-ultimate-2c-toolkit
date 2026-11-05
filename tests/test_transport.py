# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import unittest

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

    def test_device_info_fields(self):
        d = transport.DeviceInfo(vendor=0x2DC8, product=0x310A, usage_page=0xFF7A, transport="USB", name="x", handle=None)
        self.assertEqual((d.vendor, d.product, d.usage_page), (0x2DC8, 0x310A, 0xFF7A))


if __name__ == "__main__":
    unittest.main()
