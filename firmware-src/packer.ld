/* SPDX-License-Identifier: GPL-3.0-or-later
 * Placement of each tweak's code in the controller v1.09 image. noop_write and rumble_write share 0x18390 (one or
 * the other is placed), so the link uses --no-check-sections. main_tick runs from RAM at 0x1738, stored at image
 * 0x7738 (dead RAM-code functions 0x1738-0x17d4). The Home ring's code runs in place from the blank 0x18400-0x18ff0,
 * with rumble_tail first; its state and level word are in the dead RAM code at 0x1640-0x16d4 (image 0x7640). */
SECTIONS
{
	.packer 0xb908 : { *(.text.pack_xbox) *(.text.put16) *(.text.trig) *(.text.hat) *(.rodata.btn_src) }
	.noop 0x18390 : { *(.text.noop_write) }
	.rumble 0x18390 : { *(.text.rumble_write) *(.text.rumble_level) }
	.led 0x1738 : AT(0x7738) { *(.text.main_tick) }
	.hook 0xa43c : { *(.hook) }
	.ringhook 0xd4f0 : { *(.ringhook) }
	.vhooka 0xf83c : { *(.vhooka) }
	.vhookb 0xf842 : { *(.vhookb) }
	.pollhook 0xa484 : { *(.pollhook) }
	.hgamea 0xdce6 : { *(.hgamea) }
	.hgameb 0xeaf4 : { *(.hgameb) }
	.hbuzza 0xa0f8 : { *(.hbuzza) }
	.hbuzzb 0xdaa8 : { *(.hbuzzb) }
	.hidle 0xd1c8 : { *(.hidle) }
	.hstickl 0xa90 : AT(0x6a90) { *(.hstickl) }
	.hstickr 0xabc : AT(0x6abc) { *(.hstickr) }
	.hscan 0xc910 : { *(.hscan) }
	.ringtail 0x18400 : { *(.text.rumble_tail) *(.text*) *(.rodata*) }
	.rest : { *(.text*) *(.data*) *(.bss*) *(COMMON) }
	/DISCARD/ : { *(.comment) }
}
ASSERT(SIZEOF(.packer) <= 0xbad4 - 0xb908, "packer overflows the stock slot")
ASSERT(pack_xbox == 0xb908, "pack_xbox is not first in the slot")
ASSERT(noop_write == 0x18390 && rumble_write == 0x18390, "write callbacks not at 0x18390")
ASSERT(SIZEOF(.rumble) <= 0x18400 - 0x18390, "rumble_write overflows the image tail")
ASSERT(main_tick == 0x1738 && SIZEOF(.led) <= 0x17d4 - 0x1738, "main_tick outside the dead RAM-code functions")
ASSERT(SIZEOF(.hook) == 4, "hook is one tjl")
ASSERT(rumble_tail == 0x18400, "rumble_tail is not first in the blank area")
ASSERT(SIZEOF(.ringtail) <= 0x18ff0 - 0x18400, "the Home ring's code overflows the blank area")
ASSERT(SIZEOF(.ringhook) == 4 && SIZEOF(.vhooka) == 4 && SIZEOF(.vhookb) == 4 && SIZEOF(.pollhook) == 4, "a hook isn't one tjl")
ASSERT(SIZEOF(.hgamea) == 4 && SIZEOF(.hgameb) == 4 && SIZEOF(.hbuzza) == 4 && SIZEOF(.hbuzzb) == 4 && SIZEOF(.hidle) == 4 && SIZEOF(.hstickl) == 4 && SIZEOF(.hstickr) == 4 && SIZEOF(.hscan) == 4, "a settings hook isn't one tjl")
ASSERT(SIZEOF(.rest) == 0, "unplaced code or data")
