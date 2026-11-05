# Firmware sources

Our own code for the controller (Telink TC32, firmware 1.09). The built binaries are committed in
`u2c_customfw/firmware/blobs/` with a `MANIFEST` of their SHA-256, so users never need this toolchain.

| Blob | Placed at | What it is |
| --- | --- | --- |
| `packer.bin` | image `0xb908` (the stock Bluetooth packer's slot, up to `0xbad4`) | `pack_xbox`: the 16-byte Xbox Series X\|S input report |
| `report-map.bin` | `0x18274` (zero tail after the image) | the Xbox Series X\|S HID report map (283 bytes, captured by xpadneo) |
| `noop.bin` | `0x18390` | `noop_write`: accept output-report writes and ignore them |
| `rumble.bin` | `0x18390` | `rumble_write`: Xbox rumble to the motor setter `0xfa68`, the Xbox duration as its hold |
| `led.bin` | image `0x7738`, run address `0x1738` | `main_tick`: LED pins to weak drive strength, then the motor routine `0xfaa0` |
| `hook.bin` | `0xa43c` | the main loop's call, redirected from `0xfaa0` to `main_tick` |
| `ring.bin` | image `0x7640`, run address `0x1640` | `ring_led`: the Home ring on PWM1 at the level stored at image `0x76d0` (RAM `0x8416d0`), otherwise the stock LED driver |
| `ringhook.bin` | `0xd4f0` | the LED task's call for the ring, redirected from `0xd36c` to `ring_led` |

## Build

Telink's `tc32-elf-gcc` 4.5.1 and binutils come from [flyskywhy/tc32](https://github.com/flyskywhy/tc32). On a Mac, the
`macos` branch (commit `fdb1e7e`, x86-64 binaries, runs with Rosetta) needs no VM, and gave the same bytes as the Linux
binaries (commit `8ec375bb`) for every blob that existed when it was compared:

```bash
git clone --depth 1 -b macos https://github.com/flyskywhy/tc32.git /some/path/tc32
PATH="/some/path/tc32/bin:$PATH" firmware-src/build.sh /tmp/u2c-blobs
PYTHONPATH=. python3 tools/make_constants.py ultimate-2c-controller-v1.09.dat   # when an edit region changes
```

The linker's warning that `.rumble` overlaps a previous section is expected: `noop.bin` and `rumble.bin` are alternatives.

## Test

`python3 firmware-src/test.py` compiles `packer.c` natively (`-DHOST`) and checks every field of the input report
against a model built from `report-map.hex`, the rumble handler against the Xbox rumble report, and `ring_led` against
the PWM1 and PB7 registers.
