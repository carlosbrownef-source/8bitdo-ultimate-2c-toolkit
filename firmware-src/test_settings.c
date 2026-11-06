/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Native tests of settings.c (cc -DHOST). Run by test.py. Each test starts from a blank sector and a fresh RAM state. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "settings.h"

extern struct settings settings_ram;
extern u16 IDLE_LIMIT;
void settings_reset_for_test(void);
void settings_poll(void);
void settings_vendor(u8 *p);
void game_motor(u32 s, u32 w, u32 h);
void connect_buzz(u32 s, u32 w, u32 h);

static u8 flash[0x1000];
static int erases, writes, unlocks, motors;
static u32 last_s, last_w, last_h;
static int failed, ran;

void flash_unlock(void) { unlocks++; }
void flash_erase(u32 a) { if (a != SECTOR) abort(); erases++; memset(flash, 0xff, sizeof flash); }
void flash_write(u32 a, u32 n, u8 *b) { if (a != SECTOR || n != RECORD_SIZE || unlocks == 0 || erases == 0) abort(); writes++; memcpy(flash, b, n); }
void flash_read(u32 a, u32 n, u8 *b) { if (a != SECTOR) abort(); memcpy(b, flash, n); }
u32 stock_crc(u8 *p, u32 n)
{
	u32 c = 0xffff, i, k;
	for (i = 0; i < n; i++) {
		c ^= p[i];
		for (k = 0; k < 8; k++)
			c = c & 1 ? (c >> 1 ^ 0x8408) & 0xffff : c >> 1;
	}
	return (c >> 8 | c << 8) & 0xffff;
}
void motor_set(u32 s, u32 w, u32 h) { motors++; last_s = s; last_w = w; last_h = h; }

static void valid_record(int field, int value)
{
	static const u8 d[F_REMAP] = {14, 14, 100, 100, 0, 0, 0, 0, 100, 0, 100, 100, 15, 1};
	u32 c, i;
	memset(flash, 0xff, sizeof flash);
	memcpy(flash, "U2CS", 4);
	flash[4] = 1;
	memcpy(flash + 5, d, F_REMAP);
	for (i = 0; i < REMAP_SIZE; i++)
		flash[5 + F_REMAP + i] = i;
	if (field >= 0)
		flash[5 + field] = value;
	c = stock_crc(flash, 33);
	flash[33] = c;
	flash[34] = c >> 8;
}

static void cmd(int a, int b, int c)
{
	u8 p[64] = {0x81, 5, 0};
	p[3] = a; p[4] = b; p[5] = c;
	settings_vendor(p);
}

#define S settings_ram
#define CHECK(x) do { if (!(x)) { printf("%s: line %d: %s\n", __func__, __LINE__, #x); failed++; return; } } while (0)

static void start(void) { settings_poll(); }

static void load_defaults_on_blank(void)
{
	start();
	CHECK(S.loaded == 1 && S.f[F_DZ_L] == 14 && S.f[F_OUTER_R] == 100 && S.f[F_IDLE_MIN] == 15 && S.f[F_BUZZ] == 1);
	CHECK(S.f[F_REMAP] == 0 && S.f[F_REMAP + 13] == 13 && writes == 0);
}

static void load_defaults_on_bad_crc(void)
{
	valid_record(F_DZ_L, 20);
	flash[33] ^= 1;
	start();
	CHECK(S.f[F_DZ_L] == 14);
}

static void load_defaults_on_future_version(void)
{
	u32 c;
	valid_record(F_DZ_L, 20);
	flash[4] = 2;
	c = stock_crc(flash, 33);
	flash[33] = c; flash[34] = c >> 8;
	start();
	CHECK(S.f[F_DZ_L] == 14);
}

static void load_defaults_on_field_out_of_range(void)
{
	valid_record(F_DZ_L, 31);
	start();
	CHECK(S.f[F_DZ_L] == 14);
	settings_reset_for_test();
	valid_record(F_REMAP + 2, 14);
	start();
	CHECK(S.f[F_REMAP + 2] == 2);
}

static void load_defaults_after_a_cut_between_erase_and_write(void)
{
	memset(flash, 0xff, sizeof flash);
	memcpy(flash, "U2CS", 4); /* the write stopped partway */
	start();
	CHECK(S.f[F_DZ_L] == 14);
}

static void load_valid_record(void)
{
	valid_record(F_DZ_R, 7);
	start();
	CHECK(S.f[F_DZ_R] == 7 && S.f[F_DZ_L] == 14);
	settings_reset_for_test();
	valid_record(F_REMAP + 3, 0xff);
	start();
	CHECK(S.f[F_REMAP + 3] == 0xff);
}

static void set_field_applies_at_once(void)
{
	start();
	cmd(0x54, F_VIBRATION, 50);
	CHECK(S.f[F_VIBRATION] == 50 && writes == 0 && erases == 0);
}

static void set_rejects_out_of_range(void)
{
	static const u8 bad[][2] = {{F_DZ_L, 31}, {F_DZ_R, 255}, {F_OUTER_L, 69}, {F_OUTER_R, 101}, {F_CURVE_L, 3}, {F_INVERT, 16},
		{F_LT_START, 41}, {F_LT_END, 59}, {F_RT_START, 41}, {F_RT_END, 101}, {F_VIBRATION, 101}, {F_IDLE_MIN, 0}, {F_IDLE_MIN, 61},
		{F_BUZZ, 2}, {F_REMAP, 14}, {F_REMAP + 13, 254}};
	u8 before[F_COUNT];
	u32 i;
	start();
	memcpy(before, S.f, F_COUNT);
	for (i = 0; i < sizeof bad / sizeof bad[0]; i++)
		cmd(0x54, bad[i][0], bad[i][1]);
	CHECK(!memcmp(before, S.f, F_COUNT));
}

static void set_rejects_unknown_field(void)
{
	u8 before[sizeof(struct settings)];
	start();
	memcpy(before, &S, sizeof before);
	cmd(0x54, F_COUNT, 0);
	cmd(0x54, 255, 0);
	CHECK(!memcmp(before, &S, sizeof before));
}

static void commands_before_loading_are_ignored(void)
{
	cmd(0x54, F_VIBRATION, 50);
	cmd(0x55, 0, 0);
	CHECK(S.f[F_VIBRATION] == 0 && S.save == 0);
}

static void other_reports_are_ignored(void)
{
	u8 p[8] = {0x82, 5, 0, 0x54, F_VIBRATION, 50};
	start();
	settings_vendor(p);
	p[0] = 0x81; p[1] = 4;
	settings_vendor(p);
	p[1] = 5; p[2] = 1;
	settings_vendor(p);
	CHECK(S.f[F_VIBRATION] == 100);
}

static void save_waits_for_poll(void)
{
	u32 c;
	start();
	cmd(0x54, F_DZ_L, 9);
	cmd(0x55, 0, 0);
	CHECK(writes == 0 && erases == 0);
	settings_poll();
	CHECK(unlocks == 1 && erases == 1 && writes == 1);
	CHECK(!memcmp(flash, "U2CS\1", 5) && flash[5 + F_DZ_L] == 9 && flash[35] == 0xff);
	c = stock_crc(flash, 33);
	CHECK(flash[33] == (c & 0xff) && flash[34] == c >> 8);
	settings_poll();
	CHECK(writes == 1);
}

static void saved_record_loads_back(void)
{
	start();
	cmd(0x54, F_IDLE_MIN, 30);
	cmd(0x55, 0, 0);
	settings_poll();
	settings_reset_for_test();
	start();
	CHECK(S.f[F_IDLE_MIN] == 30 && IDLE_LIMIT == 17999);
}

static void reset_restores_defaults_and_saves(void)
{
	start();
	cmd(0x54, F_DZ_L, 9);
	cmd(0x54, F_REMAP, 5);
	cmd(0x56, 0, 0);
	settings_poll();
	CHECK(S.f[F_DZ_L] == 14 && S.f[F_REMAP] == 0 && writes == 1 && flash[5 + F_DZ_L] == 14);
}

static void vibration_scales_games(void)
{
	start();
	cmd(0x54, F_VIBRATION, 50);
	game_motor(200, 100, 7);
	CHECK(last_s == 100 && last_w == 50 && last_h == 7);
	cmd(0x54, F_VIBRATION, 0);
	game_motor(200, 100, 7);
	CHECK(last_s == 0 && last_w == 0 && last_h == 7);
	cmd(0x54, F_VIBRATION, 100);
	game_motor(255, 1, 0);
	CHECK(last_s == 255 && last_w == 1 && last_h == 0);
}

static void vibration_before_loading_is_unscaled(void)
{
	game_motor(200, 100, 7);
	CHECK(last_s == 200 && last_w == 100);
}

static void buzz_off_skips_motor(void)
{
	start();
	cmd(0x54, F_BUZZ, 0);
	connect_buzz(60, 60, 20);
	CHECK(motors == 0);
	cmd(0x54, F_BUZZ, 1);
	connect_buzz(60, 60, 20);
	CHECK(motors == 1 && last_s == 60 && last_h == 20);
}

static void buzz_before_load_runs(void)
{
	connect_buzz(60, 60, 20);
	CHECK(motors == 1);
}

static void idle_limit_values(void)
{
	CHECK(IDLE_LIMIT == 0); /* unset: the stub uses the stock 8999 */
	start();
	CHECK(IDLE_LIMIT == 8999);
	cmd(0x54, F_IDLE_MIN, 5);
	CHECK(IDLE_LIMIT == 2999);
	cmd(0x54, F_IDLE_MIN, 60);
	CHECK(IDLE_LIMIT == 35999);
}

typedef void (*test_fn)(void);
static const test_fn tests[] = {
	load_defaults_on_blank, load_defaults_on_bad_crc, load_defaults_on_future_version, load_defaults_on_field_out_of_range,
	load_defaults_after_a_cut_between_erase_and_write, load_valid_record, set_field_applies_at_once, set_rejects_out_of_range,
	set_rejects_unknown_field, commands_before_loading_are_ignored, other_reports_are_ignored, save_waits_for_poll,
	saved_record_loads_back, reset_restores_defaults_and_saves, vibration_scales_games, vibration_before_loading_is_unscaled,
	buzz_off_skips_motor, buzz_before_load_runs, idle_limit_values,
};

int main(void)
{
	u32 i;
	for (i = 0; i < sizeof tests / sizeof tests[0]; i++) {
		memset(flash, 0xff, sizeof flash);
		erases = writes = unlocks = motors = 0;
		last_s = last_w = last_h = 0;
		settings_reset_for_test();
		tests[i]();
		ran++;
	}
	printf("%d tests, %d failed\n", ran, failed);
	return failed != 0;
}
