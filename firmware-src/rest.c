// SPDX-License-Identifier: GPL-3.0-or-later
/* Processor rest: a watchdog fed from the main loop's 100 ms branch, and a stall of the CPU after the Bluetooth work.
 * Both live in dead RAM code (packer.ld), so the Home ring's code and its hooks keep their 0.4 bytes: the watchdog at run
 * address 0x20 (image 0x6020, the unused suspend routine's stall), the stall at 0x248c (image 0x848c, an unused
 * memcmp). Build: build.sh; test: test.py. */
typedef unsigned char u8;
typedef unsigned short u16;
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

#if defined(STALL_TEST) && !defined(HOST)
/* Test build only (tools/stalltest in the private notes): two chords on the physical button word, held for 30 calls (3 s).
 * L4 + R4 + Select hangs for ever without feeding, so the watchdog should end it in about 3 s. L4 + R4 + Start turns the
 * watchdog off, freezes 30 s on the 16 MHz system tick and comes back, and the next rest_poll arms it again. Runs from RAM
 * in .led (packer.ld), so it needs the dimmer LEDs installed. */
#define RAW_BTN (*(volatile u32 *)0x84344c)
#define HELD (*(volatile u8 *)0x84167f) /* a free byte after the Home ring's state */
#define TIMER (*(volatile u32 *)0x800740)
#define CHORD (1u << 26 | 1u << 25) /* L4 + R4 */
#define SELECT (1u << 3)
#define START 1u

__attribute__((noinline)) void test_chords(u32 b)
{
	u32 start;

	if ((b & CHORD) != CHORD || !(b & (SELECT | START))) {
		HELD = 0;
		return;
	}
	if (HELD >= 30)
		return;
	if (++HELD < 30)
		return;
	if (b & SELECT)
		for (;;)
			asm volatile("");
	TIMERS[2] &= ~0x80;
	start = TIMER;
	while (TIMER - start < 480000000u)
		;
}
#endif

#if defined(STALL_METER) && !defined(HOST)
/* Stall meter test build only (tools/stalltest in the private notes): the share of time the CPU spent stalled, in percent,
 * sent over Bluetooth in place of the battery level, which the host then logs. The firmware sends that level every
 * 0xa9ab5000 ticks (177.9 s, literal at 0xa308), and only then asks for it, so each value covers the time since the last.
 * Both run from RAM in .led (packer.ld), so it needs the dimmer LEDs installed and leaves out the test chords. The count
 * sits in the free part of the Home ring's state, zeroed at boot. */
#define METER (*(volatile u32 *)0x841670) /* stalled 16 MHz ticks since the last value */
#define SYSTICK (*(volatile u32 *)0x800740)

void stall_hook(void);

void meter_stall(void)
{
	u32 t = SYSTICK;

	stall_hook();
	t = SYSTICK - t;
	if (t > 800) /* 50 us: a pass that doesn't stall returns in a few */
		METER += t;
}

u32 meter_level(void)
{
	u32 v = (METER >> 8) * 75 >> 23; /* ticks * 100 / 2.86e9: within 1 % of the 177.9 s period */

	METER = 0;
	return v;
}
#endif

/* Every 100 ms in both positions: a watchdog fed only in the Bluetooth branch would reset the controller as soon as the
 * cable went in, and a hang anywhere in the main loop stops this feed. Stock turns the watchdog off at boot. Bits 24-27
 * of the word clear on write, so they're written as 0. */
void rest_poll(void)
{
	volatile u8 *t = TIMERS;

#if defined(STALL_TEST) && !defined(HOST)
	test_chords(RAW_BTN);
#endif
	if (REST_FLAG != 1)
		return;
	if (!(t[2] & 0x80)) { /* bit 23: the watchdog is off */
		*(volatile u32 *)(t + 0x18) = 0;
		*(volatile u32 *)t = (*(volatile u32 *)t & ~(0x3fffu << 9) & 0x00ffffff) | WD_UNITS << 9 | 1 << 6 | 1u << 23;
	}
	t[3] = WD_FEED;
}

#if defined(BATT_LOG) && !defined(HOST)
/* Battery log test build only (tools/stalltest in the private notes), run in place from the dead soft-float subtraction at
 * 0x9964 (packer.ld): once a minute while the controller is on, an 8-byte
 * record appended to the blank flash at 0x53000-0x73000 (above the copy of the original firmware, used by nothing), read
 * back later from a full backup: power-on number, half the connection interval in us / 32 (0x842e00), minutes since
 * power-on (u16), battery mV (u16, 0x843424), the firmware's percentage (0x843415), and flags: 1 external power (PD0),
 * 2 connected over Bluetooth, 4 a rumble hold running. It stops when the area is full. Its state sits in the free part of
 * the Home ring's state, zeroed at boot. */
#define LOG_START 0x53000
#define LOG_END 0x73000
#define LOG ((volatile u32 *)0x841670) /* +0 next free record (0 until found), +4 100 ms calls this minute, +8 minutes since
                                        * power-on, +12 this power-on's number */
#define FLASH_WRITE(a, n, d) ((void (*)(u32, u32, u8 *))*(volatile u32 *)0x842e3c)(a, n, d)
void flash_unlock(void);       /* 0xbd00 */
int stock_connected_bt(void);  /* 0xa28c */

__attribute__((noinline)) void battlog_poll(void)
{
	volatile u32 *l = LOG;
	u32 a = l[0], r[2];

	if (!a) { /* flash reads as memory: the code itself runs from it */
		for (a = LOG_START; a < LOG_END && *(volatile u32 *)a != 0xffffffff; a += 8)
			;
		if (a > LOG_START)
			l[3] = (*(volatile u8 *)(a - 8) + 1) & 0xff;
		l[0] = a;
	}
	if (++l[1] < 600)
		return;
	l[1] = 0;
	l[2] = l[2] + 1;
	if (a >= LOG_END)
		return;
	r[0] = l[3] | (*(volatile u32 *)0x842e00 >> 5 & 0xff) << 8 | l[2] << 16;
	r[1] = (*(volatile u32 *)0x843424 & 0xffff) | *(volatile u8 *)0x843415 << 16
	       | ((*IO(0x800518) & 1) | (stock_connected_bt() ? 2 : 0) | (MOTOR_HOLD ? 4 : 0)) << 24;
	flash_unlock();
	FLASH_WRITE(a, 8, (u8 *)r);
	l[0] = a + 8;
}
#endif

/* The main loop's call at 0xa484 comes here instead of main_poll, which it still makes. */
void rest_main_poll(void)
{
#if defined(BATT_LOG) && !defined(HOST)
	battlog_poll();
#endif
	rest_poll();
	main_poll();
}

/* In place of the Bluetooth branch's call to motor_set(0, 0, 0) at 0xa4ae, which it still makes. That call stores the
 * three zeros unless a hold is running, so afterwards rumble is active exactly when the hold is non-zero. Then, on battery
 * and with the motors still, the CPU stops for up to STALL_MS ms: timer0, the radio or the system timer wakes it, through
 * the wake mask 0x800078 (bits 0, 13 and 20). The system timer starts each Bluetooth connection event: waking even
 * slightly after it misses the Mac's packet, and the link drops within a second (tried without it). The interrupt mask 0x800640 is left alone: the stock handler has no timer0 case, so an
 * enabled, unhandled timer0 interrupt could re-enter for ever. */
void stall_hook(void)
{
	volatile u8 *t = TIMERS, *lo = IO(0x800060); /* +0xf the CPU stop, +0x18 the wake mask */

	motor_set(0, 0, 0);
	if (STALL_MS == 0 || (*IO(0x800518) & 1) || MOTOR_HOLD)
		return;
	OPAQUE(t);
	OPAQUE(lo);
	*(volatile u32 *)(lo + 0x18) = 1 << 20 | 1 << 13 | 1;
	*(volatile u32 *)(t + 0x10) = 0;
	*(volatile u32 *)(t + 4) = STALL_MS * SCLK_PER_MS;
	t[3] = 1;
	t[0] |= 1; /* timer0 on, through the low byte only: the word also holds the watchdog */
	lo[0xf] = 0x80;
	TNOP();
	TNOP();
	TNOP();
	TNOP();
	t[3] = 1;
	t[0] &= ~1;
}
