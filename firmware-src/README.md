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

## Build

Telink's `tc32-elf-gcc` 4.5.1 and binutils (flyskywhy/tc32, commit `8ec375bb`) are x86-64 Linux binaries; on a Mac
they run in a Lima VM with Rosetta. If the VM cannot see this repository, copy the folder in and the blobs out:

```bash
limactl copy -r firmware-src tc32:~/u2c/ && limactl shell tc32 -- bash -lc 'mkdir -p ~/u2c/u2c_customfw/firmware/blobs && ~/u2c/firmware-src/build.sh /tmp/u2c-blobs'
for f in packer noop rumble led hook report-map; do limactl copy tc32:~/u2c/u2c_customfw/firmware/blobs/$f.bin u2c_customfw/firmware/blobs/; done
limactl copy tc32:~/u2c/u2c_customfw/firmware/blobs/MANIFEST u2c_customfw/firmware/blobs/
```

## Test

`python3 firmware-src/test.py` compiles `packer.c` natively (`-DHOST`) and checks every field of the input report
against a model built from `report-map.hex`, and the rumble handler against the Xbox rumble report.
