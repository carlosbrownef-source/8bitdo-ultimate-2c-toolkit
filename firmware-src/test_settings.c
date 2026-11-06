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
u32 stick_left(int x, int y);
u32 stick_right(int x, int y);
u32 stick_shape(int x, int y, u32 side);
void scan_hook(u32 *word, u8 *lt, u8 *rt);
u8 DZ_OFF, RECORD_DZ;
u32 MAP_R4_A, MAP_R4_B, MAP_L4_A, MAP_L4_B;
u8 MAP_TABLE[0x9c] __attribute__((aligned(4)));
u32 stock_isqrt(u32 v);

static u8 flash[0x1000];
static int erases, writes, unlocks, motors;
static u32 last_s, last_w, last_h;
static int failed, ran, stock_limit_calls, stock_scan_calls;
static u32 stock_seen_word;
static u8 stock_seen_lt, stock_seen_rt;

/* 0x6890, as read in the disassembly: the 14 % radial dead zone rescaled to full range, or none with the switch at 1. */
static u32 stock_formula(int x, int y)
{
	int ox = x, oy = y, dx, dy;
	if (DZ_OFF == 1) {
		dx = ox + 0x7fff; dy = oy + 0x7fff;
	} else {
		unsigned long long s = (unsigned long long)x * x + (unsigned long long)y * y;
		u32 r, f;
		if ((u32)s <= 0x1410db8)
			return 0x7fff | 0x7fff << 16;
		r = stock_isqrt((u32)s);
		f = (u32)(((r - 4587) * 32767u) / 0x6e14);
		f = f * 1000 / r;
		dx = (int)(f * ox) / 1000 + 0x7fff;
		dy = (int)(f * oy) / 1000 + 0x7fff;
	}
	if (dx > 0xffff) dx = 0xffff;
	if (dx < 0) dx = 0;
	if (dy > 0xffff) dy = 0xffff;
	if (dy < 0) dy = 0;
	return (u32)dx | (u32)dy << 16;
}
u32 stock_limit(int x, int y) { stock_limit_calls++; return stock_formula(x, y); }
void stock_scan(u32 *w, u8 *lt, u8 *rt) { stock_scan_calls++; stock_seen_word = *w; stock_seen_lt = *lt; stock_seen_rt = *rt; }

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
static int mapping_saves, record_saves;
void stock_save_mappings(void) { mapping_saves++; }
void save_settings(void) { record_saves++; }
void motor_set(u32 s, u32 w, u32 h) { motors++; last_s = s; last_w = w; last_h = h; }

u32 stock_isqrt(u32 v)
{
	u32 r = 0, bit = 1u << 30;
	while (bit > v) bit >>= 2;
	while (bit) {
		if (v >= r + bit) { v -= r + bit; r = (r >> 1) + bit; } else r >>= 1;
		bit >>= 2;
	}
	return r;
}

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

#define X(v) ((int)((v) & 0xffff))
#define Y(v) ((int)((v) >> 16))
#define SET(f, v) cmd(0x54, f, v)

static void default_calls_stock(void)
{
	start();
	CHECK(stick_left(100, 200) == stock_formula(100, 200) && stock_limit_calls == 1);
	CHECK(stick_right(9000, -9000) == stock_formula(9000, -9000) && stock_limit_calls == 2);
}

static void not_loaded_calls_stock(void)
{
	stick_left(100, 200);
	stick_right(100, 200);
	CHECK(stock_limit_calls == 2);
}

static void only_the_changed_stick_leaves_stock(void)
{
	start();
	SET(F_DZ_L, 5);
	stick_right(100, 200);
	CHECK(stock_limit_calls == 1);
	stick_left(100, 200);
	CHECK(stock_limit_calls == 1);
	SET(F_DZ_L, 14);
	stick_left(100, 200);
	CHECK(stock_limit_calls == 2);
}

/* Stock rounds its scale to thousandths, so it's up to |axis| / 1000 away from the exact value: about 40 of 65535 at most. */
static void custom_matches_stock_formula_within_its_rounding(void)
{
	int x, y;
	start();
	for (x = -40000; x <= 40000; x += 1730)
		for (y = -40000; y <= 40000; y += 1913) {
			u32 a = stick_shape(x, y, 0), b = stock_formula(x, y);
			CHECK(abs(X(a) - X(b)) <= 45 && abs(Y(a) - Y(b)) <= 45);
		}
}

static void inside_dead_zone_is_centre(void)
{
	start();
	CHECK(stick_shape(4000, 2000, 0) == (0x7fff | 0x7fff << 16));
	SET(F_DZ_L, 30);
	CHECK(stick_shape(9000, 0, 0) == (0x7fff | 0x7fff << 16));
	CHECK(stick_shape(10000, 0, 0) != (0x7fff | 0x7fff << 16));
}

static void dead_zone_switch_means_zero(void)
{
	start();
	SET(F_DZ_L, 30);
	DZ_OFF = 1;
	CHECK(X(stick_shape(1000, 0, 0)) == 0x7fff + 1000);
	DZ_OFF = 0;
}

static void zero_dead_zone_is_exact(void)
{
	start();
	SET(F_DZ_L, 0);
	CHECK(X(stick_shape(1234, -4321, 0)) == 0x7fff + 1234 && Y(stick_shape(1234, -4321, 0)) == 0x7fff - 4321);
	CHECK(stick_shape(0, 0, 0) == (0x7fff | 0x7fff << 16));
}

static void outer_limit_reaches_full_at_limit(void)
{
	start();
	SET(F_OUTER_L, 80);
	SET(F_DZ_L, 0);
	CHECK(X(stick_shape(26213, 0, 0)) >= 0xfffd);
	CHECK(X(stick_shape(13106, 0, 0)) < 0xc000 && X(stick_shape(13106, 0, 0)) > 0xbff0);
	CHECK(X(stick_shape(32767, 0, 0)) == 0xffff);
}

static void curves_at_half_and_ends(void)
{
	int half, linear;
	start();
	SET(F_DZ_L, 0);
	linear = X(stick_shape(16000, 0, 0));
	SET(F_CURVE_L, 1);
	half = X(stick_shape(16000, 0, 0));
	CHECK(half < linear - 1000);
	CHECK(X(stick_shape(32767, 0, 0)) == 0xfffe || X(stick_shape(32767, 0, 0)) == 0xffff);
	SET(F_CURVE_L, 2);
	half = X(stick_shape(16000, 0, 0));
	CHECK(half > linear + 1000);
	CHECK(X(stick_shape(32767, 0, 0)) >= 0xfffd);
	CHECK(stick_shape(0, 0, 0) == (0x7fff | 0x7fff << 16));
}

static void curves_are_monotonic(void)
{
	int c, x;
	start();
	SET(F_DZ_L, 5);
	for (c = 0; c < 3; c++) {
		int last = -1;
		SET(F_CURVE_L, c);
		for (x = 0; x <= 40000; x += 100) {
			int v = X(stick_shape(x, 0, 0));
			CHECK(v >= last);
			last = v;
		}
	}
}

static void a_curve_keeps_the_direction(void)
{
	u32 v;
	start();
	SET(F_CURVE_L, 1);
	v = stick_shape(10000, 10000, 0);
	CHECK(X(v) == Y(v) && X(v) > 0x7fff);
	v = stick_shape(-10000, 10000, 0);
	CHECK(X(v) < 0x7fff && Y(v) > 0x7fff);
}

static void invert_each_axis(void)
{
	u32 p, q;
	start();
	SET(F_DZ_L, 0);
	SET(F_DZ_R, 0);
	p = stick_shape(5000, 6000, 0);
	SET(F_INVERT, 1);
	q = stick_shape(5000, 6000, 0);
	CHECK(X(q) == 0xffff - X(p) && Y(q) == Y(p));
	SET(F_INVERT, 2);
	q = stick_shape(5000, 6000, 0);
	CHECK(X(q) == X(p) && Y(q) == 0xffff - Y(p));
	SET(F_INVERT, 4);
	q = stick_shape(5000, 6000, 1);
	CHECK(X(q) == 0xffff - X(p) && Y(q) == Y(p));
	q = stick_shape(5000, 6000, 0);
	CHECK(q == p);
	SET(F_INVERT, 8);
	q = stick_shape(5000, 6000, 1);
	CHECK(X(q) == X(p) && Y(q) == 0xffff - Y(p));
}

static void invert_alone_makes_a_stick_custom(void)
{
	start();
	SET(F_INVERT, 1);
	stick_left(5000, 0);
	CHECK(stock_limit_calls == 0);
	stick_right(5000, 0);
	CHECK(stock_limit_calls == 1);
}

static void huge_input_doesnt_overflow(void)
{
	static const int v[][2] = {{60000, 60000}, {-60000, 60000}, {60000, -60000}, {-60000, -60000}, {90000, 0}, {0, -90000}};
	u32 i, o;
	start();
	SET(F_DZ_L, 0);
	SET(F_OUTER_L, 70);
	for (i = 0; i < 6; i++) {
		o = stick_shape(v[i][0], v[i][1], 0);
		if (v[i][0]) CHECK(v[i][0] > 0 ? X(o) == 0xffff : X(o) == 0);
		if (v[i][1]) CHECK(v[i][1] > 0 ? Y(o) == 0xffff : Y(o) == 0);
	}
}

static void trigger_default_untouched(void)
{
	u32 w = 0x1234;
	u8 lt = 100, rt = 200;
	start();
	scan_hook(&w, &lt, &rt);
	CHECK(lt == 100 && rt == 200 && w == 0x1234 && stock_scan_calls == 1);
	CHECK(stock_seen_lt == 100 && stock_seen_rt == 200 && stock_seen_word == 0x1234);
}

static void trigger_before_loading_untouched(void)
{
	u32 w = 0;
	u8 lt = 100, rt = 200;
	scan_hook(&w, &lt, &rt);
	CHECK(lt == 100 && rt == 200 && stock_scan_calls == 1);
}

static void trigger_start_end_scale(void)
{
	u32 w = 0;
	u8 lt, rt;
	start();
	SET(F_LT_START, 20); /* 51 of 255 */
	SET(F_LT_END, 60);   /* 153 of 255 */
	lt = 51; rt = 77;
	scan_hook(&w, &lt, &rt);
	CHECK(lt == 0 && rt == 77);
	lt = 102; rt = 77;
	scan_hook(&w, &lt, &rt);
	CHECK(lt == 127 || lt == 128);
	CHECK(stock_seen_lt == lt);
}

static void trigger_clamped(void)
{
	u32 w = 0;
	u8 lt, rt;
	start();
	SET(F_RT_START, 40);
	SET(F_RT_END, 60);
	lt = 9; rt = 0;
	scan_hook(&w, &lt, &rt);
	CHECK(rt == 0 && lt == 9);
	rt = 255;
	scan_hook(&w, &lt, &rt);
	CHECK(rt == 255);
	rt = 153;
	scan_hook(&w, &lt, &rt);
	CHECK(rt == 255);
}

static void map_cmd(int slot, u32 mask)
{
	u8 p[64] = {0x81, 5, 0, 0x57};
	p[4] = slot; p[5] = mask; p[6] = mask >> 8; p[7] = mask >> 16; p[8] = mask >> 24;
	settings_vendor(p);
}

#define LIVE_R4() (*(u16 *)(MAP_TABLE + 134) | (u32)*(u16 *)(MAP_TABLE + 136) << 16)
#define LIVE_L4() (MAP_TABLE[147] | (*(u32 *)(MAP_TABLE + 148) & 0xffffff) << 8)

static void mapping_sets_four_variables_and_live_table(void)
{
	start();
	*(u32 *)(MAP_TABLE + 148) = 0xaa000000; /* its top byte belongs to something else */
	map_cmd(0, 0x2001);
	CHECK(MAP_R4_A == 0x2001 && MAP_R4_B == 0x2001 && LIVE_R4() == 0x2001);
	map_cmd(1, 0xc000);
	CHECK(MAP_L4_A == 0xc000 && MAP_L4_B == 0xc000 && LIVE_L4() == 0xc000);
	CHECK(MAP_TABLE[151] == 0xaa);
	CHECK(mapping_saves == 0);
}

static void mapping_to_none_restores_default(void)
{
	start();
	map_cmd(0, 0x2001);
	map_cmd(0, 0);
	CHECK(MAP_R4_A == 1u << 25 && MAP_R4_B == 1u << 25 && LIVE_R4() == 1u << 25);
	map_cmd(1, 0);
	CHECK(MAP_L4_A == 1u << 26 && MAP_L4_B == 1u << 26 && LIVE_L4() == 1u << 26);
}

static void mapping_refuses_bad_slot_and_bits(void)
{
	start();
	MAP_R4_A = MAP_L4_A = 77;
	map_cmd(2, 1);
	map_cmd(0, 0x10000);
	map_cmd(1, 1u << 26);
	CHECK(MAP_R4_A == 77 && MAP_L4_A == 77);
}

static void save_persists_mappings_with_stock(void)
{
	start();
	map_cmd(0, 1);
	cmd(0x55, 0, 0);
	settings_poll();
	CHECK(mapping_saves == 1 && writes == 1 && record_saves == 0);
}

static void dead_zone_command_sets_both_places(void)
{
	start();
	cmd(0x58, 1, 0);
	CHECK(DZ_OFF == 1 && RECORD_DZ == 1);
	cmd(0x58, 0, 0);
	CHECK(DZ_OFF == 0 && RECORD_DZ == 0);
	cmd(0x58, 2, 0);
	CHECK(DZ_OFF == 0 && RECORD_DZ == 0);
}

static void save_keeps_the_dead_zone_switch_only_when_it_changed(void)
{
	start();
	cmd(0x55, 0, 0);
	settings_poll();
	CHECK(record_saves == 0);
	cmd(0x58, 1, 0);
	cmd(0x55, 0, 0);
	settings_poll();
	CHECK(record_saves == 1);
	cmd(0x55, 0, 0);
	settings_poll();
	CHECK(record_saves == 1);
}

static void reset_restores_mappings_and_dead_zone(void)
{
	start();
	map_cmd(0, 1);
	map_cmd(1, 2);
	cmd(0x58, 1, 0);
	cmd(0x56, 0, 0);
	settings_poll();
	CHECK(MAP_R4_A == 1u << 25 && MAP_L4_B == 1u << 26 && LIVE_L4() == 1u << 26 && DZ_OFF == 0 && RECORD_DZ == 0);
	CHECK(mapping_saves == 1 && record_saves == 1 && writes == 1);
}

static void start_applies_the_stored_dead_zone_switch(void)
{
	RECORD_DZ = 1; /* stock only applies it in the 2.4 GHz position (0xd644) */
	start();
	CHECK(DZ_OFF == 1);
	settings_reset_for_test();
	RECORD_DZ = 0;
	DZ_OFF = 1;
	start();
	CHECK(DZ_OFF == 0);
}

typedef void (*test_fn)(void);
static const test_fn tests[] = {
	load_defaults_on_blank, load_defaults_on_bad_crc, load_defaults_on_future_version, load_defaults_on_field_out_of_range,
	load_defaults_after_a_cut_between_erase_and_write, load_valid_record, set_field_applies_at_once, set_rejects_out_of_range,
	set_rejects_unknown_field, commands_before_loading_are_ignored, other_reports_are_ignored, save_waits_for_poll,
	saved_record_loads_back, reset_restores_defaults_and_saves, vibration_scales_games, vibration_before_loading_is_unscaled,
	buzz_off_skips_motor, buzz_before_load_runs, idle_limit_values,
	default_calls_stock, not_loaded_calls_stock, only_the_changed_stick_leaves_stock, custom_matches_stock_formula_within_its_rounding,
	inside_dead_zone_is_centre, dead_zone_switch_means_zero, zero_dead_zone_is_exact, outer_limit_reaches_full_at_limit,
	curves_at_half_and_ends, curves_are_monotonic, a_curve_keeps_the_direction, invert_each_axis, invert_alone_makes_a_stick_custom,
	huge_input_doesnt_overflow, trigger_default_untouched, trigger_before_loading_untouched, trigger_start_end_scale, trigger_clamped,
	mapping_sets_four_variables_and_live_table, mapping_to_none_restores_default, mapping_refuses_bad_slot_and_bits, save_persists_mappings_with_stock,
	dead_zone_command_sets_both_places, save_keeps_the_dead_zone_switch_only_when_it_changed, reset_restores_mappings_and_dead_zone,
	start_applies_the_stored_dead_zone_switch,
};

int main(void)
{
	u32 i;
	for (i = 0; i < sizeof tests / sizeof tests[0]; i++) {
		memset(flash, 0xff, sizeof flash);
		erases = writes = unlocks = motors = 0;
		last_s = last_w = last_h = 0;
		stock_limit_calls = stock_scan_calls = 0;
		DZ_OFF = RECORD_DZ = 0;
		mapping_saves = record_saves = 0;
		memset(MAP_TABLE, 0, sizeof MAP_TABLE);
		settings_reset_for_test();
		tests[i]();
		ran++;
	}
	printf("%d tests, %d failed\n", ran, failed);
	return failed != 0;
}
