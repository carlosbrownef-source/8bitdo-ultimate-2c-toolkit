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

@ Controller settings: calls that used to go straight to the motor setter 0xfa68.
	.section .hgamea, "ax"
	tjl	game_motor
	.section .hgameb, "ax"
	tjl	game_motor
	.section .hbuzza, "ax"
	tjl	connect_buzz
	.section .hbuzzb, "ax"
	tjl	connect_buzz

@ 0xd1c8 loaded the idle counter into r2 and the limit 8999 into r3 for the compare after it. This loads the limit from the
@ settings, or the stock value until they're loaded. It doesn't touch the other registers.
	.section .hidle, "ax"
	tjl	idle_limit
	.section .text.idle_limit, "ax"
	.global idle_limit
idle_limit:
	tloadrh	r2, [r4, #0]
	tloadr	r3, .Lidle_var
	tloadrh	r3, [r3, #0]
	tcmp	r3, #0
	tjne	.Lidle_done
	tloadr	r3, .Lidle_stock
.Lidle_done:
	tjex	lr
	.align	2
.Lidle_var:
	.word	0x8416ce
.Lidle_stock:
	.word	8999
