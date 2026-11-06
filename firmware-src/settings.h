/* SPDX-License-Identifier: GPL-3.0-or-later */
/* What's kept in flash at 0x7a000 and in RAM at 0x841680. See settings.c. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

#define SECTOR 0x7a000
#define RECORD_SIZE 35
#define REMAP_SIZE 14

enum {
	F_DZ_L, F_DZ_R, F_OUTER_L, F_OUTER_R, F_CURVE_L, F_CURVE_R, F_INVERT,
	F_LT_START, F_LT_END, F_RT_START, F_RT_END, F_VIBRATION, F_IDLE_MIN, F_BUZZ,
	F_REMAP, /* then one for each of word bits 0-13 */
	F_COUNT = F_REMAP + REMAP_SIZE
};

struct settings {
	u32 magic; /* "U2CS" */
	u8 version;
	u8 f[F_COUNT];
	u8 crc[2]; /* of everything above; RECORD_SIZE bytes up to here */
	u8 loaded, save, reset, was_connected;
	u8 stick_custom[2], triggers_custom, remap_custom; /* zero: the hook just runs stock code */
	u16 reference[4];
};
