// SPDX-License-Identifier: GPL-3.0-or-later
/* Bluetooth input report of an Xbox Series X|S controller (045e:0b13), built from the 8BitDo Ultimate 2C's state.
 * Replaces the stock BLE packer at image 0xb908 (controller v1.09) in place; its one caller (0xa2e4) is unchanged.
 * Layout = report 1 of report-map.hex (16 bytes, the report ID travels in the GATT Report Reference):
 *   0-7 LX LY RX RY u16 (0 = left/up)   8-9 LT, 10-11 RT u10   12 hat 1-8 (0 = centred)
 *   13-14 buttons 1-15 (A B - X Y - LB RB - - View Menu Xbox LS RS)   15 bit 0 Share
 * 2C state, read from the stock packers: sticks u16 with X reversed (0 = right) and Y 0 = up; triggers u8 in the
 * low byte (LT 0x84340e, RT 0x8433e8); button word 0x84342c (bits: 0 Start, 1 L3, 2 R3, 3 Select, 4 X, 5 Y,
 * 6 right, 7 left, 8 down, 9 up, 10 L1, 11 R1, 12 B, 13 A, 17 Home). L4/R4 and digital L2/R2 are left out:
 * a real pad never sets buttons 3, 6, 9, 10. Build: build.sh (tc32); test: test.py (native, -DHOST).
 * Each tweak's code is its own section (packer.ld): pack_xbox, noop_write or rumble_write, main_tick, the Home ring. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

#ifdef HOST
extern u32 BTN;
extern u16 LX, LY, RX, RY, LT, RT;
#else
#define BTN (*(volatile u32 *)0x84342c)
#define LX (*(volatile u16 *)0x8433ec)
#define LY (*(volatile u16 *)0x8433f6)
#define RX (*(volatile u16 *)0x8433e4)
#define RY (*(volatile u16 *)0x8433e6)
#define LT (*(volatile u16 *)0x84340e)
#define RT (*(volatile u16 *)0x8433e8)
#endif


int ble_notify(int conn, int handle, u8 *p, int len); /* 0x1458c, the stock packer's send */
void after_notify(int r);                              /* 0x1abc, called after it with its result */

static const u8 btn_src[15] = {13, 12, 32, 4, 5, 32, 10, 11, 32, 32, 3, 0, 17, 1, 2}; /* 32 = never set */

static void put16(u8 *p, u32 v)
{
	p[0] = v;
	p[1] = v >> 8;
}

static u32 trig(u32 v) /* u8 -> u10 */
{
	v &= 0xff;
	return v << 2 | v >> 6;
}

static u32 hat(u32 b) /* same priority as the stock packer: diagonals first */
{
	u32 u = b >> 9 & 1, r = b >> 6 & 1, d = b >> 8 & 1, l = b >> 7 & 1;
	if (u && r) return 2;
	if (d && r) return 4;
	if (d && l) return 6;
	if (u && l) return 8;
	if (u) return 1;
	if (r) return 3;
	if (d) return 5;
	if (l) return 7;
	return 0;
}

int pack_xbox(void)
{
	u8 r[16];
	u32 b = BTN, bits = 0, k;
	int ret;

	put16(r + 0, 0xffff - LX);
	put16(r + 2, LY);
	put16(r + 4, 0xffff - RX);
	put16(r + 6, RY);
	put16(r + 8, trig(LT));
	put16(r + 10, trig(RT));
	r[12] = hat(b);
	for (k = 0; k < 15; k++)
		if (btn_src[k] < 32 && (b >> btn_src[k] & 1))
			bits |= 1u << k;
	put16(r + 13, bits);
	r[15] = 0;
	ret = ble_notify(0x40, 0x1d, r, 16);
	after_notify(ret);
	return ret;
}

/* Write callback for the output report when rumble is off: accept the write and ignore it (stock firmware has no
 * callback and rejects the write). Same address as rumble_write; the patcher places one or the other. */
int noop_write(u8 *p)
{
	(void)p;
	return 0;
}

/* Write callback for the output report (rumble, report 3): jgus found that running the motors during
 * a Bluetooth connection hangs the 2C. Value: [0] enable mask (1 weak, 2 strong, 4/8 triggers), [1] [2] trigger
 * magnitudes, [3] strong, [4] weak (Xbox 0-100), [5] duration, [6] delay, [7] loop. The packet is Telink's ATT write:
 * L2CAP length at [2..3], value from [9] (jgus). motor_set(large, small, hold) as the cable 360 path calls it, whose
 * strengths are 0-255 (the 360 scale; f93c turns s into 20 + 80*s/255 % duty, or 13 + 45*s/255 % in mode 1, after a
 * short 95 % start), so magnitudes are scaled by 2.5 and capped at RUMBLE_CAP on that scale. In Bluetooth mode the
 * main loop calls motor_set(0, 0, 0) on every pass (0xa4ae), which only takes effect while no hold is running, so
 * the Xbox duration (10 ms units, as the hold counter) is passed as the hold; a stop gets hold 1 (ends in 10 ms). */
#ifndef RUMBLE_CAP
#define RUMBLE_CAP 255
#endif
void motor_set(u32 strong, u32 weak, u32 hold); /* 0xfa68 */
void ring_command(u32 level, u32 save);
void rumble_tail(u8 *p);                        /* 0x18400 */
void game_motor(u32 strong, u32 weak, u32 hold);
#ifdef HOST
extern u32 RING_CODE;
#else
#define RING_CODE (*(volatile u32 *)0x18400)    /* blank if the Home ring tweak isn't installed */
#endif

__attribute__((noinline)) static u32 rumble_level(u32 m) /* Xbox 0-100 -> 360 0-255, capped; one copy, in rumble.bin */
{
	m = m * 5 / 2;
	return m < RUMBLE_CAP ? m : RUMBLE_CAP;
}

int rumble_write(u8 *p)
{
	u8 *v = p + 9;

	if ((p[2] | p[3] << 8) < 3 + 6) /* opcode + handle + at least 6 value bytes (up to the duration) */
		return 0;
	if (RING_CODE != 0xffffffff && RING_CODE)
		rumble_tail(p);
	else if (!(v[0] & 0x80))
		motor_set(rumble_level(v[0] & 2 ? v[3] : 0), rumble_level(v[0] & 1 ? v[4] : 0), v[5] ? v[5] : 1);
	return 0;
}

/* First in the blank area, at a fixed address: rumble_write calls it when that code is there. No rumble mask uses bit 7,
 * which marks a Home ring command: level, then save. Otherwise the games' rumble, at the chosen intensity. */
void rumble_tail(u8 *p)
{
	u8 *v = p + 9;

	if (v[0] & 0x80)
		ring_command(v[1], v[2]);
	else
		game_motor(rumble_level(v[0] & 2 ? v[3] : 0), rumble_level(v[0] & 1 ? v[4] : 0), v[5] ? v[5] : 1);
}

/* Dimmer LEDs: the LED task (0xd4d0 -> 0xd36c) switches three plain GPIO outputs on and off (PB7, PD5, PF1; pin ID
 * = port << 8 | bit, output register 0x800503 + 8 * port). Their drive strength (GPIO block + 5) is set to weak here.
 * main_tick replaces the main loop's call to the motor routine at 0xa43c (hook.s), so it runs in every mode. It lives
 * in the dead RAM-code functions at run address 0x1738 (image 0x7738), copied to RAM at boot, so this tweak needs no
 * other one. */
#ifndef HOST
void motor_tick(void); /* 0xfaa0 */

void main_tick(void)
{
#ifdef STACK_TEST
	*(volatile u32 *)0x8416c8 += 1; /* passes of the main loop: does the CPU ever sleep? settings.c answers with it */
#endif
	*(volatile u8 *)0x80050d &= ~0x80; /* PB7 */
	*(volatile u8 *)0x80051d &= ~0x20; /* PD5 */
	*(volatile u8 *)0x80052d &= ~0x02; /* PF1 */
	motor_tick();
}
#endif

/* Home ring: the LED task's call for the ring (0xd4f0, PB7) comes to ring_tick instead of the stock driver 0xd36c, every
 * 200 ms. Register use follows supercypok/ultimate2c-ring (MIT), reimplemented here. The code runs in place from the
 * blank 0x18400-0x18ff0, and its state lives in dead RAM code at 0x841640 (image 0x7640). The firmware's own blink modes
 * (2, 3) keep their stock driver; otherwise PB7 goes to PWM1 at the current level, in thousandths. Motors use PWM4/5
 * and share only the clock, which isn't touched.
 *
 * The level changes with L4 + R4 (the physical word has L4 at bit 26 and R4 at bit 25, measured), the marked Bluetooth
 * report in rumble_write, or 81 05 00 52 <level> by cable, where 81 05 00 53 saves. Settings field +25 keeps the level
 * in its low nibble and, in the high one, the level installed when it was saved: installing another level wins and
 * replaces the save, or the app's choice would be ignored after any save, and an old save could come back later.
 *
 * Battery alerts, when 0x18ff0 is 1: slow blink while charging, fast blink at 15 % or less, and pulses. Charging is PD0
 * high with the charged latch 0x843423 clear (see 0xb4fc). Values come from trying them on the controller. */
#define RING_LEVELS 6
#define RING_NORMAL 0xffff
#define ALERT_LEVEL 10   /* for alerts when the ring is off */
#define SAVE_TICKS 15    /* 3 s after the last change */
#define START_TICKS 15   /* the percentage isn't reliable right after starting */
#define CHARGE_MIN_TICKS 150 /* 30 s charging before "completed" counts */
#define REPEAT_TICKS 1500    /* 5 minutes */
#define PULSE_STRENGTH 200
#define PULSE_SHORT 20   /* 10 ms units */
#define PULSE_LONG 50
#define PULSE_GAP 3      /* ticks after a pulse ends, before the next */
#define TICKS_10MS 160000  /* the system timer runs at 16 MHz */
#define L4 (1u << 26)
#define R4 (1u << 25)

enum { ALERT_NONE, ALERT_CHARGING, ALERT_LOW, ALERT_VERY_LOW };

struct ring_state {
	u8 init, level, installed, phase, alert, save_wait, q_short, q_long;
	u8 gap, ext_prev, full_done;
	u16 charge_ticks, repeat;
	u32 prev_btn, stop_at, ticks;
};
typedef char ring_state_fits[sizeof(struct ring_state) <= 0x40 ? 1 : -1]; /* the settings follow, at 0x841680 */

void led_driver(u32 mode, u32 pin, u8 *counter); /* 0xd36c */
void save_settings(void);                        /* 0xd538 */
void stock_chords(void);                         /* 0xcfa4, the main loop's Start + Select check */
void stock_vendor_a(u8 *p);                      /* 0xf56c */
void stock_vendor_b(u8 *p);                      /* 0xf594 */
void settings_poll(void);
void settings_vendor(u8 *p);
void rest_poll(void);

#ifdef HOST
#include <string.h>
extern unsigned char REGS[];
extern volatile u16 RING_LEVEL;
extern u8 PCT, FULL, SAVED, ALERTS_FLAG;
extern u32 TIMER, RAW_BTN;
static struct ring_state ring_s;
#define S ring_s
#define IO(a) (REGS + ((a) - 0x800000))
void ring_reset(void) { memset(&ring_s, 0, sizeof ring_s); }
unsigned ring_level_now(void) { return ring_s.level; }
#else
#define S (*(struct ring_state *)0x841640) /* not volatile: nothing here waits in a loop for another context's change */
#define RING_LEVEL (*(volatile u16 *)0x8416d0)  /* image 0x76d0: the level installed */
#define PCT (*(volatile u8 *)0x843415)
#define FULL (*(volatile u8 *)0x843423)
#define SAVED (*(volatile u8 *)0x843929)        /* settings record +25 */
#define ALERTS_FLAG (*(volatile u8 *)0x18ff0)
#define TIMER (*(volatile u32 *)0x800740)
#define RAW_BTN (*(volatile u32 *)0x84344c)     /* what's physically pressed: stock clears a mapped paddle's bit in BTN */
#define IO(a) ((volatile u8 *)(a))
#endif

static const u16 ring_levels[RING_LEVELS] = {RING_NORMAL, 250, 50, 10, 1, 0};

void ring_command(u32 level, u32 save)
{
	if (level < RING_LEVELS)
		S.level = level;
	if (save)
		S.save_wait = 1; /* flash waits for the LED task, in the main loop */
}

static void ring_init(void)
{
	u32 i, saved = SAVED;

	S.init = 1;
	S.installed = 0;
	for (i = 0; i < RING_LEVELS; i++)
		if (ring_levels[i] == RING_LEVEL)
			S.installed = i;
	S.level = S.installed;
	if (saved >> 4 == S.installed && (saved & 15) < RING_LEVELS)
		S.level = saved & 15;
	else if (saved != 0xff && saved >> 4 != S.installed)
		S.save_wait = 1;
	S.ext_prev = *IO(0x800518) & 1;
}

/* From the main loop's slow branch, every 100 ms (0xa460). */
void main_poll(void)
{
	u32 b = RAW_BTN, pressed = b & ~S.prev_btn;

	rest_poll();
	S.prev_btn = b;
	if (S.init && (b & L4) && (b & R4) && (pressed & (L4 | R4))) {
		S.level = S.level + 1 < RING_LEVELS ? S.level + 1 : 0;
		S.save_wait = SAVE_TICKS;
	}
	/* Only the Bluetooth path stops the motors when a hold runs out: elsewhere the strengths stay until changed. */
	if (S.stop_at && (int)(TIMER - S.stop_at) >= 0) {
		S.stop_at = 0;
		motor_set(0, 0, 1);
	}
	settings_poll();
	stock_chords();
}

static void pulse_now(u32 hold)
{
	motor_set(PULSE_STRENGTH, PULSE_STRENGTH, hold);
	S.stop_at = (TIMER + (hold - 5) * TICKS_10MS) | 1; /* centred on the 100 ms checks; never 0, which means none */
	S.gap = PULSE_GAP;
}

static void pulses(void)
{
	if (S.stop_at) {
		return;
	} else if (S.gap) {
		S.gap = S.gap - 1;
	} else if (S.q_long) {
		S.q_long = 0;
		pulse_now(PULSE_LONG);
	} else if (S.q_short) {
		S.q_short = S.q_short - 1;
		pulse_now(PULSE_SHORT);
	}
}

static void alerts(void)
{
	u32 ext = *IO(0x800518) & 1, full = FULL, pct = PCT, a = S.alert;

	if (ext && !S.ext_prev)
		S.q_short = 1;
	S.ext_prev = ext;
	if (!ext) {
		S.full_done = 0;
		S.charge_ticks = 0;
	} else if (!full) {
		if (S.charge_ticks < CHARGE_MIN_TICKS)
			S.charge_ticks = S.charge_ticks + 1;
	} else if (!S.full_done) {
		S.full_done = 1;
		if (S.charge_ticks >= CHARGE_MIN_TICKS)
			S.q_long = 1;
	}

	if (ext)
		a = full ? ALERT_NONE : ALERT_CHARGING;
	else if (S.ticks < START_TICKS)
		a = ALERT_NONE;
	else if (pct <= 5 || (a == ALERT_VERY_LOW && pct < 7))
		a = ALERT_VERY_LOW;
	else if (pct <= 15 || (a >= ALERT_LOW && pct < 18))
		a = ALERT_LOW;
	else
		a = ALERT_NONE;
	if (a == ALERT_VERY_LOW) {
		if (S.alert != ALERT_VERY_LOW || S.repeat >= REPEAT_TICKS) {
			S.q_short = 2;
			S.repeat = 0;
		}
		S.repeat = S.repeat + 1;
	}
	S.alert = a;
}

static void pwm_off(void)
{
	volatile u8 *pwm = IO(0x800780), *pb = IO(0x800508);
	u32 v;

	pwm[0] &= ~2;
	v = pb[6];
	v |= 0x80;
	pb[6] = v;
}

static void pwm_on(u32 v)
{
	volatile u8 *pwm = IO(0x800780), *pb = IO(0x800508);

	*(volatile u32 *)(pwm + 0x18) = 1000u << 16 | v; /* PWM1 compare, period */
	pwm[4] &= ~2;       /* PWM1 not inverted */
	pwm[6] &= ~2;
	v = pwm[0];         /* PWM1 on */
	v |= 2;
	pwm[0] = v;
	pwm[0x30] &= ~8;    /* its frame interrupt masked */
	pb[3] &= ~0x80;     /* PB7 latch low */
	pb[0x4f] = 4;       /* PB7 function: PWM1 */
	pb[6] &= ~0x80;     /* PB7 not GPIO */
}

void ring_tick(u32 mode, u32 pin, u8 *counter)
{
	u32 on, v, phase;

	if (!S.init)
		ring_init();
	S.ticks = S.ticks + 1;
	phase = S.phase;
	S.phase = phase + 1 < 10 ? phase + 1 : 0;

	if (ALERTS_FLAG == 1) {
		alerts();
		pulses();
	}
	if (S.save_wait) {
		S.save_wait = S.save_wait - 1;
		if (!S.save_wait) {
			SAVED = S.installed << 4 | S.level;
			save_settings();
		}
	}

	if (mode >= 2) {
		pwm_off();
		led_driver(mode, pin, counter);
		return;
	}
	on = mode == 1;
	if (S.alert == ALERT_CHARGING)
		on = phase < 5; /* also with the controller off and plugged in */
	else if (S.alert && on)
		on = phase & 1;
	v = ring_levels[S.level];
	if (S.alert && !v)
		v = ALERT_LEVEL;
	if (on && v == RING_NORMAL) {
		pwm_off();
		led_driver(1, pin, counter);
	} else if (on && v) {
		pwm_on(v);
	} else {
		pwm_off();
		led_driver(0, pin, counter);
	}
}

static void ring_vendor(u8 *p)
{
	if (p[0] != 0x81 || p[1] != 5 || p[2] != 0)
		return;
	if (p[3] == 0x52)
		ring_command(p[4], 0);
	else if (p[3] == 0x53)
		ring_command(0xff, 1);
	settings_vendor(p);
}

void vendor_a(u8 *p)
{
	ring_vendor(p);
	stock_vendor_a(p);
}

void vendor_b(u8 *p)
{
	ring_vendor(p);
	stock_vendor_b(p);
}
