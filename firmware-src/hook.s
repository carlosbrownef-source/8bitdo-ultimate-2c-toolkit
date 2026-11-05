@ SPDX-License-Identifier: GPL-3.0-or-later
@ Main-loop call at 0xa43c: was tjl 0xfaa0 (motor_tick), now main_tick (packer.c), which calls it after its own work.
	.section .hook, "ax"
	tjl	main_tick

@ The LED task's call for the Home ring at 0xd4f0: was tjl 0xd36c (the LED driver), now ring_led (packer.c).
	.section .ringhook, "ax"
	tjl	ring_led
