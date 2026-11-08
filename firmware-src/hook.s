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

@ Two calls in the code that runs from RAM (run address 0xa90 and 0xabc, image 0x6a90 and 0x6abc), once for each stick.
	.section .hstickl, "ax"
	tjl	stick_left
	.section .hstickr, "ax"
	tjl	stick_right

@ The button scan's call to 0xc3a8.
	.section .hscan, "ax"
	tjl	scan_hook

@ Fixes: the main loop's call to the idle task, the end of a USB connection, and the Bluetooth update's write handler.
	.section .hidletask, "ax"
	tjl	idle_task
	.section .hunplug, "ax"
	tjl	unplug_task
	.section .hota, "a"
	.word	no_write + 1

@ Stack test build only: at the entry of the dead code at 0x1210, ahead of scan_hook, a witness. Nothing should ever call this
@ address, since hscan calls scan_hook directly. If something does, it notes that and returns. It takes 12 bytes.
	.ifdef STACK_TEST
	.section .text.sram_guard, "ax"
	tloadr	r0, .Lguard_flag
	tmovs	r1, #1
	tstorerb	r1, [r0, #0]
	tjex	lr
.Lguard_flag:
	.word	0x8416cc
	.endif

@ Finer stick movement: the ADC pass before each report.
	.section .hsweep, "ax"
	tjl	two_sweeps

@ Processor rest: the main loop's call at 0xa484 goes to rest_main_poll (rest.c, RAM) instead of main_poll, which it still makes;
@ and the Bluetooth branch's call to the motor setter at 0xa4ae (was tjl 0xfa68) goes to stall_hook, which still makes it.
	.section .resthook, "ax"
	tjl	rest_main_poll
	.section .hstall, "ax"
	.ifdef STALL_METER
	tjl	meter_stall
	.else
	tjl	stall_hook
	.endif

@ Stall meter test build only: the battery notification's call to the percentage at 0xb8e8 goes to meter_level (rest.c).
	.ifdef STALL_METER
	.section .hmeter, "ax"
	tjl	meter_level
	.endif

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
