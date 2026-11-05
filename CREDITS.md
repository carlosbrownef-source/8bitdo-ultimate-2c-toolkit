# Credits

- **jgus-org/8bitdo-2c-re-flake** (MIT, https://github.com/jgus-org/8bitdo-2c-re-flake): reverse engineering of the Ultimate 2C's update protocol, bootloader protocol and recovery, and of the dual-bank flash layout. This project reimplements those protocols from jgus's notes and does not copy its code.
- **xpadneo** (https://github.com/atar-axis/xpadneo): `docs/descriptors/xbxs.md` holds the captured Xbox Series X|S Bluetooth HID report descriptor used here.
- **supercypok/ultimate2c-ring** (MIT, https://github.com/supercypok/ultimate2c-ring): the method for the Home ring tweak: driving PB7 with PWM1, the registers involved, the LED task's call at `0xd4f0` and the startup state at `0xa3fa`. This project reimplements it in its own code and does not copy its helper.
- **Crazyawk/8bitdo-ultimate2c-macos-rumble** (MIT, https://github.com/Crazyawk/8bitdo-ultimate2c-macos-rumble): the earliest public use found of the bootloader's identity query (command 8), and the idea of testing vibration both through CoreHaptics and directly.
- **vomba/8bitdo-ultimate-2c-apple** (MIT, https://github.com/vomba/8bitdo-ultimate-2c-apple): notes on that query and on the update record's pending-update fields, checked here before patching. No code was copied from either.
- **MoridaDE/8bitdo-2c-battery-tray** (MIT, https://github.com/MoridaDE/8bitdo-2c-battery-tray): the idea of showing the battery, and notes on where it can be read.
- **8BitDo**: the firmware update server (used only to download v1.09 on request) and the hardware.
- **Telink**: the tc32 toolchain (flyskywhy/tc32) used to build `firmware-src/`.
