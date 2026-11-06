@ SPDX-License-Identifier: GPL-3.0-or-later
@ Main-loop call at 0xa43c: was tjl 0xfaa0 (motor_tick), now main_tick (packer.c), which calls it after its own work.
	.section .hook, "ax"
	tjl	main_tick

@ The LED task's call for the Home ring at 0xd4f0: was tjl 0xd36c (the LED driver), now ring_tick (packer.c).
	.section .ringhook, "ax"
	tjl	ring_tick

@ The two calls that check vendor commands, at 0xf83c (was tjl 0xf56c) and 0xf842 (was tjl 0xf594).
	.section .vhooka, "ax"
	tjl	vendor_a
	.section .vhookb, "ax"
	tjl	vendor_b

@ The main loop's call at 0xa484: was tjl 0xcfa4 (the Start + Select check), now main_poll, which calls it after its own work.
	.section .pollhook, "ax"
	tjl	main_poll
