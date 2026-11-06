# Firmware sources

Our own code for the controller (Telink TC32, firmware 1.09). The built binaries are committed in
`u2c_customfw/firmware/blobs/` with a `MANIFEST` of their SHA-256, so users never need this toolchain.

| Blob | Placed at | What it is |
| --- | --- | --- |
| `packer.bin` | image `0xb908` (the stock Bluetooth packer's slot, up to `0xbad4`) | `pack_xbox`: the 16-byte Xbox Series X\|S input report |
| `report-map.bin` | `0x18274` (zero tail after the image) | the Xbox Series X\|S HID report map (283 bytes, captured by xpadneo) |
| `noop.bin` | `0x18390` | `noop_write`: accept output-report writes and ignore them |
| `rumble.bin` | `0x18390` | `rumble_write`: Xbox rumble to the motor setter `0xfa68`, the Xbox duration as its hold; through `rumble_tail` when that code is there. A report with bit 7 of its first byte set is a Home ring command instead |
| `led.bin` | image `0x7738`, run address `0x1738` | `main_tick`: LED pins to weak drive strength, then the motor routine `0xfaa0` |
| `hook.bin` | `0xa43c` | the main loop's call, redirected from `0xfaa0` to `main_tick` |
| `ringtail.bin` | `0x18400`, up to `0x18ff0` (blank on stock), run in place | the Home ring and settings: `rumble_tail` first, then `ring_tick` (PWM1 at the level, alerts and pulses, every 200 ms), `main_poll` (the L4 + R4 chord and the end of a pulse, every 100 ms) and the vendor commands. Its state is at RAM `0x841640` (dead RAM code, zeroed at image `0x7640`), the level installed at image `0x76d0`, and the saved level in settings field `+25` |
| `ringhook.bin` | `0xd4f0` | the LED task's call for the ring, redirected from `0xd36c` to `ring_tick` |
| `pollhook.bin` | `0xa484` | the main loop's call, redirected from `0xcfa4` to `main_poll`, which still calls it |
| `vhooka.bin`, `vhookb.bin` | `0xf83c`, `0xf842` | the vendor command checks, redirected from `0xf56c` and `0xf594` to `vendor_a` and `vendor_b`, which still call them |
| `hgamea.bin`, `hgameb.bin` | `0xdce6`, `0xeaf4` | the games' rumble, redirected from `0xfa68` to `game_motor` |
| `hbuzza.bin`, `hbuzzb.bin` | `0xa0f8`, `0xdaa8` | the buzz on connecting, redirected from `0xfa68` to `connect_buzz` |
| `hidle.bin` | `0xd1c8` | `idle_limit`: the idle counter and its limit, from the settings |
| `hstickl.bin`, `hstickr.bin` | image `0x6a90`, `0x6abc`, run address `0xa90`, `0xabc` | each stick's dead zone code, redirected from `0x890` to `stick_left` and `stick_right` |
| `hscan.bin` | `0xc910` | the button scan's call, redirected from `0xc3a8` to `scan_hook` |
| `hidletask.bin`, `hunplug.bin`, `hota.bin` | `0xa480`, `0xea88`, `0x178cc` | Fixes: `idle_task`, `unplug_task`, and the Bluetooth update's write handler, now `no_write` |
| `hsweep.bin` | `0xa2dc` | Finer stick movement: `two_sweeps` before each report |
| `ring02.bin`, `ringhook02.bin`, `rumble02.bin` | not installed | 0.2.0's versions, kept to recognise firmware it installed |
| `ringtail03.bin`, `ringhook03.bin`, `vhooka03.bin`, `vhookb03.bin`, `pollhook03.bin`, `rumble03.bin` | not installed | 0.3.0's versions, kept to recognise firmware it installed |

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
against a model built from `report-map.hex`, the rumble handler against the Xbox rumble report, and `ring_tick` against
the PWM1 and PB7 registers. It also compiles and runs `test_settings.c`, the tests of `settings.c`.
