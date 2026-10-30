# SPDX-License-Identifier: GPL-3.0-or-later
"""macOS IOKit HID transport, through ctypes (no dependencies).

IOKit delivers input reports through a callback on the run loop of the thread that opened the channel, so a
channel's xfer() must be called from that same thread.
"""
import ctypes as C
import time

from . import DeviceInfo, PermissionDenied

cf = C.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
iok = C.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")
P, I32, L = C.c_void_p, C.c_int32, C.c_long
for f, res, args in [
    (cf.CFStringCreateWithCString, P, [P, C.c_char_p, C.c_uint32]),
    (cf.CFStringGetCString, C.c_bool, [P, C.c_char_p, L, C.c_uint32]),
    (cf.CFNumberGetValue, C.c_bool, [P, L, P]),
    (cf.CFGetTypeID, L, [P]),
    (cf.CFNumberGetTypeID, L, []),
    (cf.CFStringGetTypeID, L, []),
    (cf.CFSetGetCount, L, [P]),
    (cf.CFSetGetValues, None, [P, P]),
    (cf.CFRunLoopGetCurrent, P, []),
    (cf.CFRunLoopRunInMode, I32, [P, C.c_double, C.c_bool]),
    (iok.IOHIDManagerCreate, P, [P, C.c_uint32]),
    (iok.IOHIDManagerSetDeviceMatching, None, [P, P]),
    (iok.IOHIDManagerOpen, I32, [P, C.c_uint32]),
    (iok.IOHIDManagerCopyDevices, P, [P]),
    (iok.IOHIDDeviceGetProperty, P, [P, P]),
    (iok.IOHIDDeviceOpen, I32, [P, C.c_uint32]),
    (iok.IOHIDDeviceClose, I32, [P, C.c_uint32]),
    (iok.IOHIDDeviceScheduleWithRunLoop, None, [P, P, P]),
    (iok.IOHIDDeviceUnscheduleFromRunLoop, None, [P, P, P]),
    (iok.IOHIDDeviceRegisterInputReportCallback, None, [P, P, L, P, P]),
    (iok.IOHIDDeviceSetReport, I32, [P, C.c_int, L, P, L]),
]:
    f.restype, f.argtypes = res, args
MODE = P.in_dll(cf, "kCFRunLoopDefaultMode")
REPORT_CB = C.CFUNCTYPE(None, P, I32, P, C.c_int, C.c_uint32, C.POINTER(C.c_uint8), L)
NOT_PERMITTED = 0xE00002E2
_managers = []  # devices stay valid while their manager is alive


def _cfstr(s):
    return cf.CFStringCreateWithCString(None, s.encode(), 0x08000100)


def _prop(dev, key):
    v = iok.IOHIDDeviceGetProperty(dev, _cfstr(key))
    if not v:
        return None
    if cf.CFGetTypeID(v) == cf.CFNumberGetTypeID():
        n = C.c_int64()
        cf.CFNumberGetValue(v, 4, C.byref(n))  # kCFNumberSInt64Type
        return n.value
    if cf.CFGetTypeID(v) == cf.CFStringGetTypeID():
        buf = C.create_string_buffer(256)
        cf.CFStringGetCString(v, buf, 256, 0x08000100)
        return buf.value.decode(errors="replace")


def list_devices():
    mgr = iok.IOHIDManagerCreate(None, 0)
    iok.IOHIDManagerSetDeviceMatching(mgr, None)  # every HID device
    iok.IOHIDManagerOpen(mgr, 0)
    _managers.append(mgr)
    devs = iok.IOHIDManagerCopyDevices(mgr)
    if not devs:
        return []
    n = cf.CFSetGetCount(devs)
    arr = (P * n)()
    cf.CFSetGetValues(devs, arr)
    return [DeviceInfo(vendor=_prop(d, "VendorID") or 0, product=_prop(d, "ProductID") or 0,
                       usage_page=_prop(d, "PrimaryUsagePage") or 0, transport=_prop(d, "Transport") or "",
                       name=_prop(d, "Product") or "", handle=d) for d in arr]


class IOKitChannel:
    def __init__(self, dev: DeviceInfo, report_id: int):
        self.dev, self.rid, self.replies = dev.handle, report_id, []
        self.buf = (C.c_uint8 * 64)()
        self.cb = REPORT_CB(self._on_report)
        r = iok.IOHIDDeviceOpen(self.dev, 0) & 0xFFFFFFFF
        if r == NOT_PERMITTED:
            raise PermissionDenied("macOS refused access to the controller: allow Input Monitoring for this app "
                                   "in System Settings > Privacy & Security > Input Monitoring, then try again")
        if r:
            raise OSError(f"cannot open the device: IOReturn {r:#x}")
        self.loop = cf.CFRunLoopGetCurrent()
        iok.IOHIDDeviceScheduleWithRunLoop(self.dev, self.loop, MODE)
        iok.IOHIDDeviceRegisterInputReportCallback(self.dev, self.buf, 64, self.cb, None)

    def _on_report(self, ctx, result, sender, rtype, rid, report, length):
        data = bytes(report[:length])
        if rid and (not data or data[0] != rid):
            data = bytes([rid]) + data
        self.replies.append(data)

    def xfer(self, report: bytes, timeout: float = 0.5) -> bytes | None:
        self.replies.clear()
        buf = (C.c_uint8 * 64).from_buffer_copy(report.ljust(64, b"\0")[:64])
        if iok.IOHIDDeviceSetReport(self.dev, 1, self.rid, buf, 64):  # kIOHIDReportTypeOutput
            return None
        end = time.monotonic() + timeout
        while not self.replies and time.monotonic() < end:
            cf.CFRunLoopRunInMode(MODE, 0.02, True)
        return self.replies[0] if self.replies else None

    def close(self) -> None:
        iok.IOHIDDeviceUnscheduleFromRunLoop(self.dev, self.loop, MODE)
        iok.IOHIDDeviceClose(self.dev, 0)


def open_channel(dev: DeviceInfo, report_id: int) -> IOKitChannel:
    return IOKitChannel(dev, report_id)
