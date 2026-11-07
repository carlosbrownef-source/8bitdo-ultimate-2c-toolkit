// SPDX-License-Identifier: GPL-3.0-or-later
/* Processor rest: a watchdog fed from the main loop's 100 ms branch, and a stall of the CPU after the Bluetooth work.
 * Both live in dead RAM code (packer.ld), so the Home ring's code and its hooks keep their 0.4 bytes: the watchdog at run
 * address 0x20 (image 0x6020, the unused suspend routine's stall), the stall at 0x248c (image 0x848c, an unused
 * memcmp). Build: build.sh; test: test.py. */
typedef unsigned char u8;
typedef unsigned int u32;

#define WD_UNITS 549 /* 2^18 sysclk ticks each: 3.0 s at 48 MHz, longer while flash work runs at 16 MHz */
#define WD_FEED 8
#ifndef STALL_MS
#define STALL_MS 1 /* 0 turns the stall off */
#endif
#define SCLK_PER_MS 48000

void motor_set(u32 strong, u32 weak, u32 hold); /* 0xfa68 */
void main_poll(void);                           /* packer.c */

#ifdef HOST
extern unsigned char REGS[];
extern u8 REST_FLAG, MOTOR_HOLD;
#define IO(a) (REGS + ((a) - 0x800000))
#define TNOP()
#else
#define REST_FLAG (*(volatile u8 *)0x18ff2)   /* 1 when the tweak is installed */
#define MOTOR_HOLD (*(volatile u8 *)0x8434f1) /* the hold that motor_set keeps, after its strengths at 0x8434ef */
#define IO(a) ((volatile u8 *)(a))
#define TNOP() asm volatile("tnop")
#endif
#define TIMERS IO(0x800620) /* +0 the enables and the watchdog capture, +3 status (clear on write), +4 timer0's capture, +0x10 its tick, +0x18 timer2's tick */
#define OPAQUE(p) asm("" : "+r"(p)) /* keeps the compiler from turning offsets off a base into one literal each */

/* Every 100 ms in both positions: a watchdog fed only in the Bluetooth branch would reset the controller as soon as the
 * cable went in, and a hang anywhere in the main loop stops this feed. Stock turns the watchdog off at boot. Bits 24-27
 * of the word clear on write, so they're written as 0. */
void rest_poll(void)
{
	volatile u8 *t = TIMERS;

	if (REST_FLAG != 1)
		return;
	if (!(t[2] & 0x80)) { /* bit 23: the watchdog is off */
		*(volatile u32 *)(t + 0x18) = 0;
		*(volatile u32 *)t = (*(volatile u32 *)t & ~(0x3fffu << 9) & 0x00ffffff) | WD_UNITS << 9 | 1 << 6 | 1u << 23;
	}
	t[3] = WD_FEED;
}

/* The main loop's call at 0xa484 comes here instead of main_poll, which it still makes. */
void rest_main_poll(void)
{
	rest_poll();
	main_poll();
}

/* In place of the Bluetooth branch's call to motor_set(0, 0, 0) at 0xa4ae, which it still makes. That call stores the
 * three zeros unless a hold is running, so afterwards rumble is active exactly when the hold is non-zero. Then, on battery
 * and with the motors still, the CPU stops for up to STALL_MS ms: timer0 or the radio wakes it, through the wake mask
 * 0x800078 (bit 0 and bit 13). The interrupt mask 0x800640 is left alone: the stock handler has no timer0 case, so an
 * enabled, unhandled timer0 interrupt could re-enter for ever. */
void stall_hook(void)
{
	volatile u8 *t = TIMERS, *lo = IO(0x800060); /* +0xf the CPU stop, +0x18 the wake mask */

	motor_set(0, 0, 0);
	if (STALL_MS == 0 || (*IO(0x800518) & 1) || MOTOR_HOLD)
		return;
	OPAQUE(t);
	OPAQUE(lo);
	*(volatile u32 *)(lo + 0x18) = 1 << 13 | 1;
	*(volatile u32 *)(t + 0x10) = 0;
	*(volatile u32 *)(t + 4) = STALL_MS * SCLK_PER_MS;
	t[3] = 1;
	*(volatile u32 *)t |= 1; /* timer0 on; whole-word writes clear any status bit 24-27 that reads as set, which nothing here needs */
	lo[0xf] = 0x80;
	TNOP();
	TNOP();
	TNOP();
	TNOP();
	t[3] = 1;
	*(volatile u32 *)t &= ~1u;
}
