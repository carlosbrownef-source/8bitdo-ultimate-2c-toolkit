# FAQ

## Installing

### macOS won't open the app

The app isn't signed, so macOS blocks it the first time. Open **System Settings → Privacy & Security**, scroll to the message about the app and click **Open Anyway**. Right-click → Open no longer works on current macOS. You can also remove the app from quarantine in Terminal, using the path where you put it:

```sh
xattr -dr com.apple.quarantine "path/to/Firmware Toolkit.app"
```

### The app doesn't see the controller or the dongle

The app needs **Input Monitoring** to talk to them: check that it's allowed in System Settings → Privacy & Security → Input Monitoring. The controller's firmware can only be read by cable, and the dongle has to be plugged in on its own, with the controller off.

## Using it

### How do I put the controller in update mode?

Turn it fully off, then hold LB + RB while you plug in the cable. The small light below the Home ring will blink white. The dongle has no buttons, so the app puts it in update mode by itself whenever it writes.

### macOS still sees the controller as a generic device over Bluetooth

macOS remembers how a Bluetooth device described itself. After installing or removing a Bluetooth tweak, remove the controller from Bluetooth settings and pair it again.

### A game doesn't vibrate over Bluetooth

Rumble over Bluetooth needs both the Xbox Series X|S tweak and the Rumble over Bluetooth tweak. Then open the Diagnostics tab and try the vibration both ways: the way a native game would, and by sending the report straight to the controller. If only the direct report vibrates, the firmware isn't the problem.

### Can I go back to the original firmware?

Yes. The bootloader, which runs update mode, is never modified, so Restore always works: it restores your own backup or 8BitDo's original firmware, 1.09 for the controller and 1.03 for the dongle. [SAFEGUARDS.md](../SAFEGUARDS.md) lists every check the app makes before it writes.

### Will 8BitDo's own apps still work?

Probably not. With the tweaks installed, the controller and the dongle report themselves differently, so the Firmware Updater and Ultimate Software may not recognise them.

## Compatibility

### Does it work with my controller?

Only with the 8BitDo Ultimate 2C Wireless on firmware 1.09 and its 2.4 GHz dongle on firmware 1.03, because those are the ones I have and could test. The app checks the device and the firmware, and won't continue with anything else. It doesn't support the Ultimate 2C Wired or other 8BitDo models.

The same approach could probably be extended to other firmware versions, and perhaps to other 8BitDo controllers, as long as their firmware isn't encrypted. If you have one and want to try, [firmware-notes.md](firmware-notes.md) explains how the firmware is laid out.

### Why is this possible at all?

The firmware of the controller and the dongle is neither encrypted nor signed: 8BitDo's update file is a plain image, and each bootloader only checks a CRC on each block it receives, so it accepts and runs a modified firmware. Each tweak here is a small, hash-checked edit to that image.

### Why only the Mac?

Out of the box, macOS and most Mac games see the Ultimate 2C as a generic HID device, not as a standard controller, and its dongle has the same problem. Windows doesn't need this: it is more flexible about detecting Xbox 360-compatible controllers by cable, and it supports Xbox 360 controllers over Bluetooth, which macOS doesn't.

### Does the app run on Linux?

No, only macOS. The only part that depends on the operating system is `u2c_customfw/transport/`, and [porting.md](porting.md) explains how to port it.

### Why are there three names?

The app is **U2C Firmware Toolkit**, the Homebrew cask and the release zips are `firmware-toolkit`, and the command-line tool and Python package keep the project's first name, `u2c-customfw`, so existing backups and macOS permissions keep working.
