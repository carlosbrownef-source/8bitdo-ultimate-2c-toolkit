# Porting to Linux

Everything outside `u2c_customfw/transport/` is portable Python (standard library only). A port adds
`u2c_customfw/transport/hidraw.py` and selects it in `transport/__init__.py::_backend`.

The controller test in the Diagnostics tab uses macOS's GameController through the Mac app's Swift code (`macos/Diagnostics.swift`), so a port doesn't get it. The page explains that where the test would be, and the rest of the tab keeps working.

It must provide:

- `list_devices() -> list[DeviceInfo]`: every HID device with `vendor`, `product`, `usage_page` (the primary usage page of its report descriptor), `transport` (a string; `"Bluetooth"` in it for Bluetooth) and `name`, plus an opaque `handle`.
- `open_channel(dev, report_id) -> Channel` where `Channel.xfer(report, timeout) -> bytes | None` sends one 64-byte output report and returns the next input report (or `None` on timeout), and `close()`.

Report IDs: the running controller's update channel (vendor usage page `0xff7a`, `2dc8:310a` or, with the cable tweak, `045e:028e`) uses output report `0x81` and returns input report `0x02` with its ID byte in front. The bootloader (`2dc8:3208`) declares 64-byte reports with no report ID: send with ID 0, replies have no ID.

On Linux this is `/dev/hidraw*` (read and write the raw report; include the report ID byte only when the device uses IDs) and needs a udev rule to give the user access. Replies arrive asynchronously, so `xfer` should write, then read with a timeout.
