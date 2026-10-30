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
 * Each tweak's code is its own section (packer.ld): pack_xbox, noop_write or rumble_write, main_tick. */
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

static u32 rumble_level(u32 m) /* Xbox 0-100 -> 360 0-255, capped */
{
	m = m * 5 / 2;
	return m < RUMBLE_CAP ? m : RUMBLE_CAP;
}

int rumble_write(u8 *p)
{
	u8 *v = p + 9;

	if ((p[2] | p[3] << 8) < 3 + 6) /* opcode + handle + at least 6 value bytes (up to the duration) */
		return 0;
	motor_set(rumble_level(v[0] & 2 ? v[3] : 0), rumble_level(v[0] & 1 ? v[4] : 0), v[5] ? v[5] : 1);
	return 0;
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
	*(volatile u8 *)0x80050d &= ~0x80; /* PB7 */
	*(volatile u8 *)0x80051d &= ~0x20; /* PD5 */
	*(volatile u8 *)0x80052d &= ~0x02; /* PF1 */
	motor_tick();
}
#endif

