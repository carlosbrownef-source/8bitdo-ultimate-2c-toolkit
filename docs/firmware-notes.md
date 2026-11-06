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
| `0x73000-0x77000`, `0x79000`, `0x7c000-0x7e000`, `0x7f000` | configuration, Bluetooth address (`0x76000`), edition (`0x77000`: 2 means WUKONG), a 12-byte record that only the bootloader uses (`0x79000`), Bluetooth pairings (`0x7c000` and, once the first sector fills, `0x7d000`; the second sector is erased at every start if it isn't blank, so nothing else can live there) |

## Update channel (running controller)

USB interface with vendor usage page `0xff7a`, 64-byte reports: output report `0x81`, input report `0x02`. Read command `81 05 05` (length at byte 6, address at bytes 14-17, at most 46 bytes), reply `02 05` with status, echoes and data from byte 18; no checksum. In v1.09 the handler has no state gate and the session start `81 05 00 21 01` only replies; other firmware states weren't checked. `81 05 c1` lifts the flash write protection until restart. `81 05 00 51 00` makes the app reboot into the bootloader (not used by this app).

## Bootloader (`2dc8:3208`)

Enter by powering the controller fully off and holding L1+R1 while plugging in the cable (white LED). One HID interface, 64-byte reports without report ID: `[0]=05 [1:3]=command [5:7]=data length [7:9]=CRC-16/MODBUS of the data [9:13]=parameter [13:17]=address [17:]=data`. Commands: 5 read (data from byte 18), 4 erase (4 KB units), 3 write (at most 46 bytes), 8 identity (data length and parameter 4; the reply has length 2 and, from byte 18, the constant `0x301b` from the bootloader itself, so damaged firmware does not change it; what the dongle answers is not known yet). Success reply: `[0]=0 [1]=5 [2]=0 [4]=command`. No signature or encryption is involved.

## Other findings

- Main loop (`0xa430`): the button/stick/rumble tasks; in Bluetooth mode it calls the motor setter with zero strength on every pass, which is why rumble is off in stock Bluetooth mode.
- Battery: `0x843415` holds the percentage and `0x843424` the voltage in mV. PD0 (`0x800518` bit 0) is external power, and `0x843423` latches when charged. The button word `0x84342c` has L4 at bit 26 and R4 at bit 25, which don't reach the Bluetooth report. A save (`0xd538`) doesn't interrupt Bluetooth: the longest gap between reports was 44 ms.
- The app area runs up to `0x19000`: `0x18400-0x19000` is blank on stock, erased with bank A, and the bootloader writes it like the rest with the same parameter. `0x19000` is where an 8BitDo update stops erasing, not a limit of the bootloader; flash above it is blank and nothing refers to it.
- LEDs are three plain GPIO outputs (PB7, PD5, PF1) switched by the LED task every 200 ms; weak drive strength dims them slightly, and the Home ring (PB7) can also be driven by PWM1 for real brightness control (`firmware-src/packer.c`, `ring_tick`). Its level is a word at image `0x76d0`, copied to RAM at `0x8416d0`.
- The Bluetooth stack is a closed Telink library; after a connection the firmware asks for a 7.5 ms interval, latency 59 and a 2 s supervision timeout (`0xa0de` calls `0x14834`, which stores the request); the link on macOS still runs at a 15 ms interval.

## Home ring protocol (our additions)

Everything here is ours, in `firmware-src/packer.c`; none of it exists in stock. The ring code sits at `0x18400` and is only present when a ring recipe is installed.

- **Level by cable**: `81 05 00 52 <level>` sets the ring level (0-5, anything higher is ignored) without saving it. `81 05 00 53` saves the current level to the settings record about three seconds later, from the LED task, so the flash write never interrupts the main loop. Both are checked after the stock handlers' dispatch in `vendor_a` and `vendor_b`, and the stock handler still runs, so the replies are the stock ones.
- **Level over Bluetooth**: the Xbox rumble output report, with the high bit (`0x80`) set in the first value byte (`p[9]`), which no rumble mask uses. `p[10]` is the level and `p[11]` is non-zero to save. `rumble_write` handles it and never starts a motor for it. It needs the ring code to be present.
- **Settings record `+25`** (`0x73019`, RAM `0x843929`): the low nibble is the saved level and the high nibble is the level installed when it was saved. A save made under another installed level is ignored at start and replaced by the installed level, so choosing a level in the app wins over an old save.
- **Alerts flag** at `0x18ff0`: `1` turns battery alerts on (slow blink while charging, fast blink at 15 % or less, pulses); anything else, including blank, leaves them off. The firmware reads it and never writes it; the app changes it with the "Battery alerts" tweak.
- **Level by buttons**: L4 and R4 pressed together step to the next level and save after 3 seconds. The button word it reads is being corrected, so don't rely on the bit numbers.

## Controller settings (our additions)

`firmware-src/settings.c`, in the tail at `0x18400-0x18ff0` with the Home ring. A record of 35 bytes at sector `0x7a000`, blank on stock and referenced by nothing else, written only by this code: `U2CS`, version 1, 28 fields (numbers and ranges in `u2c_customfw/settings.py` and `settings.c`), CRC of bytes 0-32 with the firmware's `0xaf80`, little endian. Anything else loads as defaults. In RAM at `0x841680`, in the dead RAM code after the ring's state; all zero until loaded, and zero means the hooks run stock code.

| Command, by cable, no reply | Effect |
| --- | --- |
| `81 05 00 54 <field> <value>` | Set a field in RAM, at once; out of range is ignored |
| `81 05 00 55` | Save on the next 100 ms pass: the record, then stock's mappings (`0xd7d4`), then stock's record if the dead zone switch changed (`0xd538`) |
| `81 05 00 56` | Back to defaults, mappings and dead zone switch included, then save |
| `81 05 00 57 <0 R4, 1 L4> <u32 LE>` | Mapping, bits 0-15 of the word; 0 is none. Set in stock's four variables and in the scan's live table |
| `81 05 00 58 <0, 1>` | Stock's dead zone switch: `0x8433d6` and record `+6` |

Hooks: `0x6a90`, `0x6abc` (run `0xa90`, `0xabc`) for the sticks, instead of `0x890`; `0xc910` for triggers and remapping, before `0xc3a8`; `0xdce6`, `0xeaf4` and `rumble_tail` for the games' rumble; `0xa0f8`, `0xdaa8` for the buzz on connecting; `0xd1c8` for the idle limit. The tweak `fixes`: `0xa480`, `0xea88`, and the pointer at `0x178cc`.

Dangerous commands exist on this channel, with no authentication. The app must never send, outside an update: `81 05 02/03/04/0b/c4` (they write or erase flash at `0x3f000-0x7f000`, including the MAC sector), `81 05 00 38` (moves the saved trigger endpoints each time), `81 05 00 61` (the edition at `0x77000`), `81 xx 66 AA 63/64` (`64` zeroes stock's record, and both set a tool session flag until restart).
