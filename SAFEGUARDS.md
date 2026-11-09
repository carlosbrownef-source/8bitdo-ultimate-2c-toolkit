# Safeguards

These are the checks the app makes before and while it writes to the controller or the dongle. They are enforced in the code, not just recommended. For the warranty and the risks of using the app, see the [disclaimer](DISCLAIMER.md).

## The controller

- **Protected memory.** The app writes nothing below `0x6000`, where the bootloader lives, or at or above `0x73000`, where the configuration, the MAC address, the calibration and the Bluetooth pairings live. The bootloader is what runs update mode, so you can always restore.
- **The firmware's own records.** Saving a Home ring level, an L4 or R4 mapping or the dead zone switch makes the firmware rewrite its own settings record at `0x73000`, as it already does for its other settings. Saving the settings makes it write its own record at `0x7a000`, which is blank on an original controller. The app itself never writes there.
- **A backup of the same controller.** A write needs a backup of that very unit: its bootloader must match, and so must its MAC address, allowing for the small change each new pairing makes.
- **The right firmware.** The controller must be running the original firmware 1.09, with or without the tweaks.
- **A pending update.** If the controller has a firmware update pending, the app refuses to install the tweaks.
- **Never the dongle.** The controller's steps never write to the dongle. The app tells them apart by the bootloader's identity, the USB version and how the flash reads back.
- **Checked edits.** Each tweak is a set of byte edits to the original firmware 1.09, and every edit checks the original bytes it replaces before writing.
- **Restoring 8BitDo's 1.09.** The original firmware is downloaded from 8BitDo's update server, only when you ask, and checked against its known SHA-256. The app only restores it if the controller really is on 1.09, which it reads from the update record or, if that is blank, identifies by the hash of bank A or bank B. If the version can't be determined, it refuses.
- **The last resort.** *Install Firmware 1.09 Anyway…*, in the Diagnostics tab, can override an unknown version, behind a warning and a confirmation that spells out the risks. It never overrides a version that is known to be different.

## The dongle

- **A backup of the same dongle.** A write needs a backup of that very dongle: its bootloader and its calibration must match.
- **Only the firmware.** The app only rewrites the firmware (`0x6000`-`0x10000`), and writes the app header last. It never writes the update record, the second firmware copy, the calibration or the licence sector.
- **Update mode is checked.** The app puts the dongle in update mode by itself, and checks there that its update-mode code and calibration match the backup before it erases anything. After writing, it reads the firmware back and restarts the dongle.
- **An interrupted write.** If a write stops before the header is written, the dongle stays in update mode, the app says so, and Restore still works.
- **Restoring 8BitDo's 1.03.** The original firmware is rebuilt from your backup and checked against its known SHA-256, so nothing is downloaded.
- **Not while in use.** With the controller connected through the dongle, the app reads the dongle but changes nothing. Turn the controller off first.
