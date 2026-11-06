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

#ifdef HOST
#include <string.h>
struct settings settings_ram;
u16 IDLE_LIMIT;
void flash_unlock(void);
void flash_erase(u32 addr);
void flash_write(u32 addr, u32 n, u8 *data);
void flash_read(u32 addr, u32 n, u8 *data);
u32 stock_crc(u8 *p, u32 n);
extern u8 DZ_OFF, RECORD_DZ, MAP_TABLE[];
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
		S.stick_custom[i] = S.f[F_DZ_L + i] != defaults[F_DZ_L] || S.f[F_OUTER_L + i] != 100 || S.f[F_CURVE_L + i]
			|| (S.f[F_INVERT] >> (2 * i) & 3);
	S.triggers_custom = S.f[F_LT_START] || S.f[F_RT_START] || S.f[F_LT_END] != 100 || S.f[F_RT_END] != 100;
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

/* What L4 or R4 presses, as button word bits; nothing means its own bit, as stock's default. Applies at once in the scan's table. */
static void set_mapping(u32 l4, u32 mask)
{
	u8 *t = MAP_TABLE;

	if (l4) {
		mask = mask ? mask : 1u << 26;
		MAP_L4_A = MAP_L4_B = mask;
		t[147] = mask;
		*(u32 *)(t + 148) = (*(u32 *)(t + 148) & 0xff000000) | mask >> 8;
	} else {
		mask = mask ? mask : 1u << 25;
		MAP_R4_A = MAP_R4_B = mask;
		*(u16 *)(t + 134) = mask;
		*(u16 *)(t + 136) = mask >> 16;
	}
}

static void set_dead_zone_off(u32 off)
{
	DZ_OFF = RECORD_DZ = off;
	S.dz_changed = 1;
}

static void load(void)
{
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
		stock_save_mappings();
		if (S.dz_changed) {
			S.dz_changed = 0;
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

/* The button scan's call to stock_scan, every 5 ms: changes go in before it, so it still works out the digital triggers,
 * mapping and turbo from them. */
void scan_hook(u32 *word, u8 *lt, u8 *rt)
{
	if (S.triggers_custom) {
		*lt = trigger(*lt, S.f[F_LT_START], S.f[F_LT_END]);
		*rt = trigger(*rt, S.f[F_RT_START], S.f[F_RT_END]);
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
