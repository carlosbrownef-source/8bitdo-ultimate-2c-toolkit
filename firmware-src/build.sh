#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the tweak blobs with Telink's tc32 toolchain (x86-64 Linux; e.g. a Lima VM) and copy them into the package:
#   build.sh [OUT_DIR]     -> OUT_DIR/*.bin and u2c_customfw/firmware/blobs/{*.bin,MANIFEST}
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "${1:-/tmp/u2c-blobs}"
out=$(cd "${1:-/tmp/u2c-blobs}" && pwd)
blobs="$here/../u2c_customfw/firmware/blobs"
cd "$here"
rm -f "$out"/*.o "$out"/*.elf "$out"/*.bin "$out"/packer.dis
tc32-elf-gcc -Os -Wall -Werror -ffreestanding -fno-builtin -ffunction-sections -fdata-sections -c packer.c -o "$out/packer.o"
tc32-elf-as hook.s -o "$out/hook.o"
tc32-elf-ld -T packer.ld --no-check-sections \
	--defsym ble_notify=0x1458c --defsym after_notify=0x1abc --defsym motor_set=0xfa68 --defsym motor_tick=0xfaa0 \
	"$out/packer.o" "$out/hook.o" -o "$out/packer.elf"
for s in packer noop rumble led hook; do tc32-elf-objcopy -O binary -j ".$s" "$out/packer.elf" "$out/$s.bin"; done
tc32-elf-objdump -d "$out/packer.elf" > "$out/packer.dis"
python3 -c "import sys; open(sys.argv[2],'wb').write(bytes.fromhex(open(sys.argv[1]).read()))" report-map.hex "$out/report-map.bin"
mkdir -p "$blobs"
cp "$out"/{packer,noop,rumble,led,hook,report-map}.bin "$blobs/"
(cd "$blobs" && sha256sum packer.bin noop.bin rumble.bin led.bin hook.bin report-map.bin > MANIFEST 2>/dev/null \
	|| shasum -a 256 packer.bin noop.bin rumble.bin led.bin hook.bin report-map.bin > MANIFEST)
ls -l "$blobs"
