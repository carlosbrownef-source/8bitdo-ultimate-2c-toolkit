// SPDX-License-Identifier: GPL-3.0-or-later
/* Processor rest: a watchdog fed from the main loop's 100 ms branch, and a stall of the CPU after the Bluetooth work.
 * Runs in place from the blank area after the image, with the Home ring (packer.ld). Build: build.sh; test: test.py. */
typedef unsigned char u8;
typedef unsigned int u32;

#define WD_UNITS 549 /* 2^18 sysclk ticks each: 3.0 s at 48 MHz, longer while flash work runs at 16 MHz */
#define WD_FEED 8

#ifdef HOST
extern unsigned char REGS[];
extern u8 REST_FLAG;
#define IO(a) (REGS + ((a) - 0x800000))
#else
#define REST_FLAG (*(volatile u8 *)0x18ff2) /* 1 when the tweak is installed */
#define IO(a) ((volatile u8 *)(a))
#endif
#define TIMERS IO(0x800620) /* +0 the enables and the watchdog capture, +3 status (clear on write), +0x18 timer2's tick */

/* From main_poll, every 100 ms in both positions: a watchdog fed only in the Bluetooth branch would reset the controller as
 * soon as the cable went in, and a hang anywhere in the main loop stops this feed. Stock turns the watchdog off at boot. Bits
 * 24-27 of the word clear on write, so they're written as 0. */
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
