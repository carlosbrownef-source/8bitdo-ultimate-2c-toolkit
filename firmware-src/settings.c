/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Controller settings: values in RAM that change at once, kept in a record at 0x7a000 that only this code writes. Runs in
 * place from the blank area after the image, with the Home ring. The state lives in dead RAM code (zero until loaded), and
 * zero means inactive, so a hook that runs before settings_poll's first pass does what stock does. See
 * docs/firmware-notes.md. Build: build.sh; test: test_settings.c, run by test.py. */
#include "settings.h"

#define MAGIC 0x53433255 /* "U2CS", little endian */
#define VERSION 1

void motor_set(u32 strong, u32 weak, u32 hold); /* 0xfa68 */
u32 stock_limit(int x, int y);                  /* 0x890, the stock dead zone: the same arguments and result as stick_left */
u32 stock_isqrt(u32 v);                         /* 0x84c */
void stock_scan(u32 *word, u8 *lt, u8 *rt);     /* 0xc3a8: digital triggers, mapping and turbo */
void stock_save_mappings(void);                 /* 0xd7d4: into stock's record, if they changed */
void save_settings(void);                       /* 0xd538: stock's record */
void stock_idle(void);                          /* 0xd190 */
int stock_connected_bt(void);                   /* 0xa28c */
int stock_connected_24g(void);                  /* 0xe088 */
void stock_da58(u32 a);                         /* 0xda58 */
void stock_reboot(void);                        /* 0xd056: inside stock's mode switch check; interrupts off, saves mappings, restarts */
void stock_sweep(void);                         /* 0xb388: one pass over the ADC channels */

#ifdef HOST
#include <string.h>
struct settings settings_ram;
u16 IDLE_LIMIT;
void flash_unlock(void);
void flash_erase(u32 addr);
void flash_write(u32 addr, u32 n, u8 *data);
void flash_read(u32 addr, u32 n, u8 *data);
u32 stock_crc(u8 *p, u32 n);
extern u8 DZ_OFF, RECORD_DZ, MAP_TABLE[], PD, SETTINGS_FLAG;
extern u16 IDLE_COUNT, STICK_LX, STICK_LY, STICK_RX, STICK_RY;
extern u32 RAW_WORD;
extern u32 MAP_R4_A, MAP_R4_B, MAP_L4_A, MAP_L4_B;
#define S settings_ram
void settings_reset_for_test(void) { memset(&S, 0, sizeof S); IDLE_LIMIT = 0; }
#else
void flash_unlock(void);       /* 0xbd00 */
void flash_erase(u32 addr);    /* 0xfe98 */
u32 stock_crc(u8 *p, u32 n);   /* 0xaf80 */
#define DZ_OFF (*(volatile u8 *)0x8433d6)      /* the firmware's dead zone switch, flipped by Start + Select */
#define RECORD_DZ (*(volatile u8 *)0x843916)   /* the same switch in stock's settings record: +6 */
#define MAP_R4_A (*(volatile u32 *)0x84346c)   /* the variables stock saves in its record: +9, cable and 2.4 GHz */
#define MAP_L4_A (*(volatile u32 *)0x843464)   /* +13 */
#define MAP_R4_B (*(volatile u32 *)0x843460)   /* +17, the Bluetooth position */
#define MAP_L4_B (*(volatile u32 *)0x843474)   /* +21 */
#define MAP_TABLE ((u8 *)0x843874)             /* the button scan's table: R4 in halfwords at +134 and +136, L4 unaligned at +147 */
#define IDLE_COUNT (*(volatile u16 *)0x843438) /* counts up in stock_idle until the limit, then off */
#define STICK_LX (*(volatile u16 *)0x8433ec)
#define STICK_LY (*(volatile u16 *)0x8433f6)
#define STICK_RX (*(volatile u16 *)0x8433e4)
#define STICK_RY (*(volatile u16 *)0x8433e6)
#define RAW_WORD (*(volatile u32 *)0x84344c)   /* what's physically pressed; bit 28 set is the Bluetooth position */
#define PD (*(volatile u8 *)0x800518)          /* bit 0: external power */
#define SETTINGS_FLAG (*(volatile u8 *)0x18ff1) /* 1 when the tweak is installed: the code is there for any Home ring level */
#define flash_write(a, n, d) ((void (*)(u32, u32, u8 *))*(volatile u32 *)0x842e3c)(a, n, d)
#define flash_read(a, n, d) ((void (*)(u32, u32, u8 *))*(volatile u32 *)0x842e50)(a, n, d)
#define S (*(struct settings *)0x841680) /* not volatile: nothing here waits in a loop for another context's change */
#define IDLE_LIMIT (*(volatile u16 *)0x8416ce) /* read by the idle_limit stub in hook.s */
typedef char settings_fit[sizeof(struct settings) <= 0x4e ? 1 : -1];
#endif

static const u8 low[F_REMAP] = {0, 0, 70, 70, 0, 0, 0, 0, 60, 0, 60, 0, 1, 0};
static const u8 high[F_REMAP] = {30, 30, 100, 100, 2, 2, 15, 40, 100, 40, 100, 100, 60, 1};
static const u8 defaults[F_REMAP] = {14, 14, 100, 100, 0, 0, 0, 0, 100, 0, 100, 100, 15, 1};

static int valid(u32 field, u32 v)
{
	if (field >= F_COUNT)
		return 0;
	if (field >= F_REMAP)
		return v < REMAP_SIZE || v == 0xff;
	return v >= low[field] && v <= high[field];
}

static void set_defaults(void)
{
	u32 i;

	for (i = 0; i < F_REMAP; i++)
		S.f[i] = defaults[i];
	for (i = 0; i < REMAP_SIZE; i++)
		S.f[F_REMAP + i] = i;
}

/* What the hooks use, worked out once rather than on every pass. */
static void changed(void)
{
	u32 i;

	IDLE_LIMIT = S.f[F_IDLE_MIN] * 600 - 1;
	for (i = 0; i < 2; i++)
		S.stick_custom[i] = S.f[F_DZ_L + i] != 14 || S.f[F_OUTER_L + i] != 100 || S.f[F_CURVE_L + i]
			|| (S.f[F_INVERT] >> (2 * i) & 3);
	S.triggers_custom = S.f[F_LT_START] || S.f[F_RT_START] || S.f[F_LT_END] != 100 || S.f[F_RT_END] != 100;
	S.remap_custom = 0;
	for (i = 0; i < REMAP_SIZE; i++)
		if (S.f[F_REMAP + i] != i)
			S.remap_custom = 1;
}

static int stored_ok(void)
{
	u8 *r = (u8 *)&S;
	u32 c = stock_crc(r, RECORD_SIZE - 2), i;

	if (S.magic != MAGIC || S.version != VERSION)
		return 0;
	if (r[RECORD_SIZE - 2] != (c & 0xff) || r[RECORD_SIZE - 1] != c >> 8)
		return 0;
	for (i = 0; i < F_COUNT; i++)
		if (!valid(i, S.f[i]))
			return 0;
	return 1;
}

/* What L4 or R4 presses, as button word bits; nothing means its own bit, as stock's default. Applies at once in the scan's table,
 * and clears any turbo on that paddle as stock does. Stock's own variables wait for a save, since it keeps them by itself when
 * it turns off or restarts. */
static void set_mapping(u32 l4, u32 mask)
{
	u8 *t = MAP_TABLE;

	if (l4) {
		mask = mask ? mask : 1u << 26;
		t[147] = mask;
		*(u32 *)(t + 148) = (*(u32 *)(t + 148) & 0xff000000) | mask >> 8;
		t[151] = 0;
	} else {
		mask = mask ? mask : 1u << 25;
		*(u16 *)(t + 134) = mask;
		*(u16 *)(t + 136) = mask >> 16;
		t[138] = 0;
	}
	S.map_pending[l4] = mask;
	S.map_changed |= 1 << l4;
}

/* Stock's record gets it on a save, because anything could save that record. */
static void set_dead_zone_off(u32 off)
{
	DZ_OFF = off;
	S.dz_changed = 1;
}

#ifdef STACK_TEST
/* Test build only: how much of the main stack, 0x843cf0-0x844000, has never been used since
 * the first pass of the main loop. It fills the deep part with a pattern, and 81 05 00 59 answers with what's still intact. */
void stock_send(u8 *data, u32 n, u32 interface); /* 0xeb7c */
void stock_clear(u8 *p, u32 value, u32 n);       /* 0x103f8, memset */
#define STACK_BOTTOM ((volatile u32 *)0x843cf0)
#define STACK_MARKED ((volatile u32 *)0x843f00)  /* the main loop's first pass is far shallower than this */
#define PAINT 0x5a5a5a5a

static void stack_paint(void)
{
	volatile u32 *p = STACK_BOTTOM;

	while (p < STACK_MARKED)
		*p++ = PAINT;
}

static void stack_answer(void)
{
	u8 r[64];
	volatile u32 *p = STACK_BOTTOM;
	u32 n;

	while (*p == PAINT && p < STACK_MARKED)
		p++;
	n = (u32)p - (u32)STACK_BOTTOM;
	stock_clear(r, 0, 64);
	r[0] = 0x59;
	r[1] = n;
	r[2] = n >> 8;
	r[3] = *(volatile u8 *)0x8416cc; /* the witness in hook.s: 1 if anything entered the dead code at 0x1210 */
	for (n = 0; n < 8; n++) /* 100 ms passes at 0x8416c4, main loop passes at 0x8416c8, since starting */
		r[4 + n] = ((volatile u8 *)0x8416c4)[n];
	stock_send(r, 63, 2);
}
#endif

static void load(void)
{
#ifdef STACK_TEST
	stack_paint();
#endif
	flash_read(SECTOR, RECORD_SIZE, (u8 *)&S);
	if (!stored_ok())
		set_defaults();
	changed();
	DZ_OFF = RECORD_DZ == 1; /* stock only applies this switch at startup in the 2.4 GHz position (0xd644) */
	S.loaded = 1;
}

static void store(void)
{
	u8 *r = (u8 *)&S;
	u32 c;

	S.magic = MAGIC;
	S.version = VERSION;
	c = stock_crc(r, RECORD_SIZE - 2);
	r[RECORD_SIZE - 2] = c;
	r[RECORD_SIZE - 1] = c >> 8;
	flash_unlock();
	flash_erase(SECTOR);
	flash_write(SECTOR, RECORD_SIZE, r);
}

/* From the main loop's slow branch, every 100 ms: flash only ever happens here. */
void settings_poll(void)
{
#ifdef STACK_TEST
	*(volatile u32 *)0x8416c4 += 1; /* 100 ms passes, to turn main_tick's count into a rate */
#endif
	if (SETTINGS_FLAG != 1)
		return;
	if (!S.loaded) {
		load();
		return;
	}
	if (S.reset) {
		S.reset = 0;
		set_defaults();
		changed();
		set_mapping(0, 0);
		set_mapping(1, 0);
		set_dead_zone_off(0);
		S.save = 1;
	}
	if (S.save) {
		S.save = 0;
		store();
		if (S.map_changed & 1)
			MAP_R4_A = MAP_R4_B = S.map_pending[0];
		if (S.map_changed & 2)
			MAP_L4_A = MAP_L4_B = S.map_pending[1];
		S.map_changed = 0;
		stock_save_mappings();
		if (S.dz_changed) {
			S.dz_changed = 0;
			RECORD_DZ = DZ_OFF;
			save_settings();
		}
	}
}

void settings_vendor(u8 *p)
{
	if (!S.loaded || p[0] != 0x81 || p[1] != 5 || p[2] != 0)
		return;
	if (p[3] == 0x54) {
		if (valid(p[4], p[5])) {
			S.f[p[4]] = p[5];
			changed();
		}
	} else if (p[3] == 0x55) {
		S.save = 1;
	} else if (p[3] == 0x56) {
		S.reset = 1;
	} else if (p[3] == 0x57) {
		u32 mask = p[5] | p[6] << 8 | (u32)p[7] << 16 | (u32)p[8] << 24;
		if (p[4] < 2 && mask <= 0xffff)
			set_mapping(p[4], mask);
	} else if (p[3] == 0x58) {
		if (p[4] < 2)
			set_dead_zone_off(p[4]);
	} else if (p[3] == 0x5a) {
		S.loaded = 0; /* read the record again on the next pass */
#ifdef STACK_TEST
	} else if (p[3] == 0x59) {
		stack_answer();
#endif
	}
}

#define FULL 32767
#define BIGGEST 46340 /* its square, twice, still fits in 32 bits */

static int limit(int v)
{
	return v > BIGGEST ? BIGGEST : v < -BIGGEST ? -BIGGEST : v;
}

/* One axis: scale, centre, clamp, and maybe invert. m is at most 0xffff and |v| at most BIGGEST, so the product fits unsigned. */
static u32 axis(int v, u32 m, u32 r, u32 invert)
{
	u32 a = (v < 0 ? -v : v) * m / r;
	int o = v < 0 ? 0x7fff - (int)a : 0x7fff + (int)a;

	o = o > 0xffff ? 0xffff : o < 0 ? 0 : o;
	return invert ? 0xffff - o : o;
}

/* The stock code's shape, with a size and a curve: nothing inside the dead zone, then the distance from the centre rescaled to
 * full range at the outer limit. Past that it keeps growing, as stock does, so the corners stay reachable. */
u32 stick_shape(int x, int y, u32 side)
{
	u32 dz = DZ_OFF == 1 ? 0 : S.f[F_DZ_L + side] * FULL / 100;
	u32 outer = S.f[F_OUTER_L + side] * FULL / 100, r, m, inv = S.f[F_INVERT] >> (2 * side);

	x = limit(x);
	y = limit(y);
	r = stock_isqrt((u32)(x * x) + (u32)(y * y));
	if (r <= dz) {
		r = 1;
		m = 0;
	} else {
		m = (r - dz) * FULL / (outer - dz);
		if (m > 0xffff)
			m = 0xffff;
		if (m < FULL) {
			u32 sq = m * m / (2 * FULL);
			if (S.f[F_CURVE_L + side] == 1)
				m = m / 2 + sq;
			else if (S.f[F_CURVE_L + side] == 2)
				m = m + m / 2 - sq;
		}
	}
	return axis(x, m, r, inv & 1) | axis(y, m, r, inv & 2) << 16;
}

u32 stick_left(int x, int y)
{
	return S.stick_custom[0] ? stick_shape(x, y, 0) : stock_limit(x, y);
}

u32 stick_right(int x, int y)
{
	return S.stick_custom[1] ? stick_shape(x, y, 1) : stock_limit(x, y);
}

static u32 trigger(u32 v, u32 start, u32 end)
{
	u32 lo = start * 255 / 100, hi = end * 255 / 100;

	return v <= lo ? 0 : v >= hi ? 255 : (v - lo) * 255 / (hi - lo);
}

/* The button scan's call to stock_scan, every 5 ms, in dead RAM code at 0x1210: changes go in before it, so it still works out the digital triggers,
 * mapping and turbo from them. */
void scan_hook(u32 *word, u8 *lt, u8 *rt)
{
	if (S.triggers_custom) {
		*lt = trigger(*lt, S.f[F_LT_START], S.f[F_LT_END]);
		*rt = trigger(*rt, S.f[F_RT_START], S.f[F_RT_END]);
	}
	if (S.remap_custom) {
		u32 w = *word, out = w & ~((1u << REMAP_SIZE) - 1), i;
		for (i = 0; i < REMAP_SIZE; i++)
			if ((w >> i & 1) && S.f[F_REMAP + i] != 0xff)
				out |= 1u << S.f[F_REMAP + i];
		*word = out;
	}
	stock_scan(word, lt, rt);
}

/* The games' rumble: the 2.4 GHz and cable calls to 0xfa68, and Bluetooth through rumble_tail. */
void game_motor(u32 strong, u32 weak, u32 hold)
{
	if (S.loaded) {
		strong = strong * S.f[F_VIBRATION] / 100;
		weak = weak * S.f[F_VIBRATION] / 100;
	}
	motor_set(strong, weak, hold);
}

/* The two calls that vibrate on connecting. */
void connect_buzz(u32 strong, u32 weak, u32 hold)
{
	if (!S.loaded || S.f[F_BUZZ])
		motor_set(strong, weak, hold);
}

/* Fixes. Moving a stick counts as using the controller, which stock only sees through buttons, so stick-only play doesn't
 * end at the limit. A worn stick drifting past the threshold isn't kept alive for long: the reference follows it. And a
 * dropped connection gets its full search time, since stock goes on counting from wherever it was. */
#define MOVED 0x1000

#ifdef STACK_TEST
void idle_task(void) { stock_idle(); } /* the test build has no room for it; it's installed without Fixes */
#else
void idle_task(void)
{
	static volatile u16 *const sticks[4] = {&STICK_LX, &STICK_LY, &STICK_RX, &STICK_RY};
	u32 connected = stock_connected_bt() || stock_connected_24g(), change = 0, i;

	for (i = 0; i < 4; i++) {
		u32 d = *sticks[i] - S.reference[i] + MOVED;
		if (d > 2 * MOVED)
			change = 1;
	}
	if (change)
		for (i = 0; i < 4; i++)
			S.reference[i] = *sticks[i];
	if ((change && connected) || (!connected && S.was_connected))
		IDLE_COUNT = 0;
	S.was_connected = connected;
	if (S.unplug_wait) {
		S.unplug_wait = S.unplug_wait - 1;
		if (!(PD & 1))
			stock_reboot();
	}
	stock_idle();
}
#endif

/* The cable stopped being a USB host. In the Bluetooth position, if the power goes too, restart: that finds the Mac at once,
 * where the firmware otherwise stays searching. The power can take a moment to fall, so idle_task keeps watching for half a
 * second. PD0 tells this from a sleeping Mac, which comes through here too and keeps its power. */
void unplug_task(u32 a)
{
	stock_da58(a);
	if (RAW_WORD >> 28 & 1)
		S.unplug_wait = 5;
}

/* Replaces the Bluetooth firmware update's write handler, which needs no encryption: any device that connects could write
 * to 0x20000-0x3f000, and finishing an update writes zeros at flash 8. */
int no_write(u8 *p)
{
	(void)p;
	return 0;
}

/* Two conversions per report, so stock's averaging in 0xb14c has something to average. */
void two_sweeps(void)
{
	stock_sweep();
	stock_sweep();
}
