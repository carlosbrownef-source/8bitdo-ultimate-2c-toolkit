/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Controller settings: values in RAM that change at once, kept in a record at 0x7a000 that only this code writes. Runs in
 * place from the blank area after the image, with the Home ring. The state lives in dead RAM code (zero until loaded), and
 * zero means inactive, so a hook that runs before settings_poll's first pass does what stock does. See
 * docs/firmware-notes.md. Build: build.sh; test: test_settings.c, run by test.py. */
#include "settings.h"

#define MAGIC 0x53433255 /* "U2CS", little endian */
#define VERSION 1

void motor_set(u32 strong, u32 weak, u32 hold); /* 0xfa68 */

#ifdef HOST
#include <string.h>
struct settings settings_ram;
u16 IDLE_LIMIT;
void flash_unlock(void);
void flash_erase(u32 addr);
void flash_write(u32 addr, u32 n, u8 *data);
void flash_read(u32 addr, u32 n, u8 *data);
u32 stock_crc(u8 *p, u32 n);
#define S settings_ram
void settings_reset_for_test(void) { memset(&S, 0, sizeof S); IDLE_LIMIT = 0; }
#else
void flash_unlock(void);       /* 0xbd00 */
void flash_erase(u32 addr);    /* 0xfe98 */
u32 stock_crc(u8 *p, u32 n);   /* 0xaf80 */
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
	IDLE_LIMIT = S.f[F_IDLE_MIN] * 600 - 1;
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

static void load(void)
{
	flash_read(SECTOR, RECORD_SIZE, (u8 *)&S);
	if (!stored_ok())
		set_defaults();
	changed();
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
		S.save = 1;
	}
	if (S.save) {
		S.save = 0;
		store();
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
	}
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
