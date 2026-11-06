#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the tweak blobs with Telink's tc32 toolchain (on PATH; see README.md) and copy them into the package:
#   build.sh [OUT_DIR]     -> OUT_DIR/*.bin and u2c_customfw/firmware/blobs/{*.bin,MANIFEST}
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "${1:-/tmp/u2c-blobs}"
out=$(cd "${1:-/tmp/u2c-blobs}" && pwd)
blobs="$here/../u2c_customfw/firmware/blobs"
cd "$here"
rm -f "$out"/*.o "$out"/*.elf "$out"/*.bin "$out"/packer.dis
tc32-elf-gcc -Os -Wall -Werror -ffreestanding -fno-builtin -ffunction-sections -fdata-sections -c packer.c -o "$out/packer.o"
tc32-elf-gcc -Os -Wall -Werror -ffreestanding -fno-builtin -ffunction-sections -fdata-sections ${EXTRA_CFLAGS:-} -c settings.c -o "$out/settings.o"
tc32-elf-as hook.s -o "$out/hook.o"
tc32-elf-ld -T packer.ld --no-check-sections \
	--defsym ble_notify=0x1458c --defsym after_notify=0x1abc --defsym motor_set=0xfa68 --defsym motor_tick=0xfaa0 --defsym led_driver=0xd36c \
	--defsym save_settings=0xd538 --defsym stock_chords=0xcfa4 --defsym stock_vendor_a=0xf56c --defsym stock_vendor_b=0xf594 \
	--defsym flash_unlock=0xbd00 --defsym flash_erase=0xfe98 --defsym stock_crc=0xaf80 --defsym stock_limit=0x890 --defsym stock_isqrt=0x84c --defsym stock_scan=0xc3a8 --defsym stock_save_mappings=0xd7d4 --defsym stock_idle=0xd190 --defsym stock_connected_bt=0xa28c --defsym stock_connected_24g=0xe088 --defsym stock_da58=0xda58 --defsym stock_reboot=0xd056 --defsym stock_sweep=0xb388 --defsym stock_send=0xeb7c --defsym stock_clear=0x103f8 --defsym __udivsi3=0x850c --defsym __divsi3=0x8504 \
	"$out/packer.o" "$out/settings.o" "$out/hook.o" -o "$out/packer.elf"
for s in packer noop rumble led hook ringtail ringhook vhooka vhookb pollhook hgamea hgameb hbuzza hbuzzb hidle hstickl hstickr hscan hidletask hunplug hota hsweep sram; do tc32-elf-objcopy -O binary -j ".$s" "$out/packer.elf" "$out/$s.bin"; done
tc32-elf-objdump -d "$out/packer.elf" > "$out/packer.dis"
python3 -c "import sys; open(sys.argv[2],'wb').write(bytes.fromhex(open(sys.argv[1]).read()))" report-map.hex "$out/report-map.bin"
if [ -n "${EXTRA_CFLAGS:-}" ] && [ -z "${TEST_COPY:-}" ]; then  # a test build mustn't replace what ships
	echo "Built in $out with $EXTRA_CFLAGS. The package's blobs are unchanged." ; exit 0
fi
mkdir -p "$blobs"
cp "$out"/{packer,noop,rumble,led,hook,ringtail,ringhook,vhooka,vhookb,pollhook,hgamea,hgameb,hbuzza,hbuzzb,hidle,hstickl,hstickr,hscan,hidletask,hunplug,hota,hsweep,sram,report-map}.bin "$blobs/"
(cd "$blobs" && { sha256sum *.bin > MANIFEST 2>/dev/null || shasum -a 256 *.bin > MANIFEST; })  # the *02.bin are 0.2.0's, kept to recognise its firmware
ls -l "$blobs"
