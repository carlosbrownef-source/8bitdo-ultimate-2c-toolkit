# Firmware notes (Ultimate 2C controller, v1.09)

What was established by disassembling 8BitDo's v1.09 image. Addresses are image addresses (flash address = image address). No 8BitDo bytes are reproduced here.

## Chip and image

- Telink B80 (TC32 instruction set, close to ARM Thumb-1 but not Thumb). The `.dat` update file is a 0x1C-byte header plus the payload, which is not encrypted, loaded at `0x6000`; the payload is 0x12400 bytes (bank A, `0x6000-0x18400`, then erased padding to `0x19000`).
- The first 0x2500 bytes of the payload (`0x6000-0x8500`) are copied to RAM and run there **at addresses `0x0-0x2500`** (CPU vectors, flash driver, interrupt handler, radio driver, analog access, reset). Reading that code at its flash address gives wrong call targets.
- RAM is 16 KB (`0x840000-0x844000`): RAM code to `0x842500`, instruction cache to `0x842e00`, initialised data, zeroed data and stacks. Of the RAM code, about 1.1 KB is unreferenced (for example run addresses `0x1640-0x16d4` and `0x1738-0x17d4`).

## Flash (512 KB)

| Range | Contents |
| --- | --- |
| `0x0-0x5000` | resident bootloader (never written) |
| `0x6000-0x18400` | app bank A (the running firmware) |
| `0x3f000` | update record (52 bytes: version at `+0x0c`, pending magic at `+0x18`, staging address `0x40000` at `+0x1c`, pending length at `+0x20`, CRC at `+0x30`). A patch is refused while a pending field is set. |
| `0x40000-0x52400` | app bank B (normal-mode updates are staged here and applied by the bootloader) |
| `0x73000-0x77000`, `0x79000`, `0x7c000`, `0x7f000` | configuration, Bluetooth address (`0x76000`), edition (`0x77000`: 2 means WUKONG), Bluetooth pairings (`0x7c000`, 64-byte records) |

## Update channel (running controller)

USB interface with vendor usage page `0xff7a`, 64-byte reports: output report `0x81`, input report `0x02`. Read command `81 05 05` (length at byte 6, address at bytes 14-17, at most 46 bytes), reply `02 05` with status, echoes and data from byte 18; no checksum. Some firmware states ignore reads until a session start `81 05 00 21 01`. `81 05 c1` lifts the flash write protection until restart. `81 05 00 51 00` makes the app reboot into the bootloader (not used by this app).

## Bootloader (`2dc8:3208`)

Enter by powering the controller fully off and holding L1+R1 while plugging in the cable (white LED). One HID interface, 64-byte reports without report ID: `[0]=05 [1:3]=command [5:7]=data length [7:9]=CRC-16/MODBUS of the data [9:13]=parameter [13:17]=address [17:]=data`. Commands: 5 read (data from byte 18), 4 erase (4 KB units), 3 write (at most 46 bytes), 8 identity (data length and parameter 4; the reply has length 2 and, from byte 18, the constant `0x301b` from the bootloader itself, so damaged firmware does not change it; what the dongle answers is not known yet). Success reply: `[0]=0 [1]=5 [2]=0 [4]=command`. No signature or encryption is involved.

## Other findings

- Main loop (`0xa430`): the button/stick/rumble tasks; in Bluetooth mode it calls the motor setter with zero strength on every pass, which is why rumble is off in stock Bluetooth mode.
- Battery: `0x843415` holds the percentage and `0x843424` the voltage in mV. PD0 (`0x800518` bit 0) is external power, and `0x843423` latches when charged. The button word `0x84342c` has L4 at bit 26 and R4 at bit 25, which reach neither the Bluetooth report nor games. A save (`0xd538`) doesn't interrupt Bluetooth: the longest gap between reports was 44 ms.
- The app area runs up to `0x19000`: `0x18400-0x19000` is blank on stock, erased with bank A, and the bootloader writes it like the rest with the same parameter.
- LEDs are three plain GPIO outputs (PB7, PD5, PF1) switched by the LED task every 200 ms; weak drive strength dims them slightly, and the Home ring (PB7) can also be driven by PWM1 for real brightness control (`firmware-src/packer.c`, `ring_led`). Its level is a word at image `0x76d0`, copied to RAM at `0x8416d0`.
- The Bluetooth stack is a closed Telink library; the firmware never requests a connection-parameter update, so macOS runs the link at a 15 ms interval.
