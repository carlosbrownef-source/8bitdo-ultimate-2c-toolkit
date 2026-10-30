/* SPDX-License-Identifier: GPL-3.0-or-later
 * Placement of each tweak's code in the controller v1.09 image. noop_write and rumble_write share 0x18390 (one or
 * the other is placed), so the link uses --no-check-sections. main_tick runs from RAM at 0x1738, stored at image
 * 0x7738 (dead RAM-code functions 0x1738-0x17d4). */
SECTIONS
{
	.packer 0xb908 : { *(.text.pack_xbox) *(.text.put16) *(.text.trig) *(.text.hat) *(.rodata*) }
	.noop 0x18390 : { *(.text.noop_write) }
	.rumble 0x18390 : { *(.text.rumble_write) *(.text.rumble_level) }
	.led 0x1738 : AT(0x7738) { *(.text.main_tick) }
	.hook 0xa43c : { *(.hook) }
	.rest : { *(.text*) *(.data*) *(.bss*) *(COMMON) }
	/DISCARD/ : { *(.comment) }
}
ASSERT(SIZEOF(.packer) <= 0xbad4 - 0xb908, "packer overflows the stock slot")
ASSERT(pack_xbox == 0xb908, "pack_xbox is not first in the slot")
ASSERT(noop_write == 0x18390 && rumble_write == 0x18390, "write callbacks not at 0x18390")
ASSERT(SIZEOF(.rumble) <= 0x18400 - 0x18390, "rumble_write overflows the image tail")
ASSERT(main_tick == 0x1738 && SIZEOF(.led) <= 0x17d4 - 0x1738, "main_tick outside the dead RAM-code functions")
ASSERT(SIZEOF(.hook) == 4, "hook is one tjl")
ASSERT(SIZEOF(.rest) == 0, "unplaced code or data")
