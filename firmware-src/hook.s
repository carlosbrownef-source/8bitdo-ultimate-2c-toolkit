@ SPDX-License-Identifier: GPL-3.0-or-later
@ Main-loop call at 0xa43c: was tjl 0xfaa0 (motor_tick), now main_tick (packer.c), which calls it after its own work.
	.section .hook, "ax"
	tjl	main_tick
