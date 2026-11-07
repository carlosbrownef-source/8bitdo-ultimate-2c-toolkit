#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native test of packer.c: compile it for the Mac (-DHOST), feed input vectors, and check each report field by field
against a model. The field layout is parsed from report-map.hex; the meaning of the 2C's state comes from the stock
firmware (360 converter, stock packer), not from the C. The TC32 build itself is done by build.sh in the VM."""
import itertools, os, random, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = r"""
#include <stdio.h>
#include <stdlib.h>
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32;
u32 BTN, RAW_BTN; u16 LX, LY, RX, RY, LT, RT;
u8 REGS[0x1000] __attribute__((aligned(4))); volatile u16 RING_LEVEL;
u8 PCT, FULL, SAVED, ALERTS_FLAG; u32 TIMER, RING_CODE = 1;
u8 REST_FLAG;
static int notifies, afters, stock_passes;
void rest_poll(void);
int pack_xbox(void);
int rumble_write(u8 *p);
void ring_tick(u32 mode, u32 pin, u8 *counter);
void ring_command(u32 level, u32 save);
void main_poll(void);
void vendor_a(u8 *p);
void vendor_b(u8 *p);
void ring_reset(void);
unsigned ring_level_now(void);
void save_settings(void) { printf("SAVE %02x\n", SAVED); }
void flash_unlock(void) {}
void flash_erase(u32 a) { printf("ERASE %x\n", a); }
void flash_write(u32 a, u32 n, u8 *d) { printf("WRITE %x\n", a); }
void flash_read(u32 a, u32 n, u8 *d) { for (u32 i = 0; i < n; i++) d[i] = 0xff; }
u32 stock_crc(u8 *p, u32 n) { return 0; }
u32 stock_limit(int x, int y) { return 0; }
u32 stock_isqrt(u32 v) { return 0; }
void stock_scan(u32 *w, u8 *lt, u8 *rt) {}
u8 DZ_OFF, RECORD_DZ, MAP_TABLE[0x9c];
u32 MAP_R4_A, MAP_R4_B, MAP_L4_A, MAP_L4_B;
void stock_save_mappings(void) {}
u8 PD, SETTINGS_FLAG = 1; u16 IDLE_COUNT, STICK_LX, STICK_LY, STICK_RX, STICK_RY; u32 RAW_WORD;
void stock_idle(void) {}
int stock_connected_bt(void) { return 0; }
int stock_connected_24g(void) { return 0; }
void stock_da58(u32 a) {}
void stock_reboot(void) {}
void stock_sweep(void) {}
void stock_chords(void) { stock_passes++; }
void stock_vendor_a(u8 *p) { printf("VA\n"); }
void stock_vendor_b(u8 *p) { printf("VB\n"); }
void led_driver(u32 mode, u32 pin, u8 *counter) { printf("D %x %x %lx\n", mode, pin, (unsigned long)counter); }
void motor_set(u32 s, u32 w, u32 h) { printf("M %u %u %u\n", s, w, h); }
int ble_notify(int conn, int handle, u8 *p, int len) {
    if (conn != 0x40 || handle != 0x1d || len != 16 || afters) { printf("bad call %x %x %d\n", conn, handle, len); exit(1); }
    for (int i = 0; i < len; i++) printf("%02x", p[i]);
    printf("\n"); notifies++; return 7;
}
void after_notify(int r) { if (r != 7 || notifies != 1) { printf("bad after\n"); exit(1); } afters++; }
__attribute__((noinline)) static void dirty(void) { volatile u8 junk[512]; for (int i = 0; i < 512; i++) junk[i] = 0xa5; }
int main(void) {
    unsigned b, lx, ly, rx, ry, lt, rt;
    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == 'L') { /* L <mode> <level> <fill>: one ring_tick call on registers all set to fill, then their state */
            unsigned mode, level, fill;
            sscanf(line + 2, "%x %x %x", &mode, &level, &fill);
            for (int i = 0; i < 0x1000; i++) REGS[i] = fill;
            ring_reset(); SAVED = 0xff; ALERTS_FLAG = 0;
            RING_LEVEL = level;
            ring_tick(mode, 0x180, (u8 *)0x3452);
            printf("%02x %02x %02x %02x %02x %02x %02x %02x%02x%02x%02x\n", REGS[0x780], REGS[0x784], REGS[0x786], REGS[0x7b0], REGS[0x50b], REGS[0x557], REGS[0x50e],
                   REGS[0x79b], REGS[0x79a], REGS[0x799], REGS[0x798]);
            continue;
        }
        if (line[0] == 'I') { /* I <installed level> <saved> <alerts> <pct> <ext> <full> */
            unsigned l, sv, al, pc, ex, fu;
            sscanf(line + 2, "%x %x %x %u %u %u", &l, &sv, &al, &pc, &ex, &fu);
            for (int i = 0; i < 0x1000; i++) REGS[i] = 0;
            ring_reset(); RING_LEVEL = l; SAVED = sv; ALERTS_FLAG = al; PCT = pc; REGS[0x518] = ex; FULL = fu; BTN = RAW_BTN = 0; TIMER = 0; stock_passes = 0; RING_CODE = 1;
            continue;
        }
        if (line[0] == 'X') { unsigned pc, ex, fu; sscanf(line + 2, "%u %u %u", &pc, &ex, &fu); PCT = pc; REGS[0x518] = ex; FULL = fu; continue; }
        if (line[0] == 'B') { sscanf(line + 2, "%x", &BTN); RAW_BTN = BTN; continue; }
        if (line[0] == 'K') { sscanf(line + 2, "%x", &RAW_BTN); continue; } /* the physical word alone */
        if (line[0] == 'Y') { sscanf(line + 2, "%x", &BTN); continue; }     /* the mapped word alone */
        if (line[0] == 'N') { RING_CODE = 0; continue; } /* no ring code installed */
        if (line[0] == 'P') { /* P <n>: n main-loop passes, 100 ms apart */
            unsigned n; sscanf(line + 2, "%u", &n);
            while (n--) { TIMER += 1600000; main_poll(); }
            continue;
        }
        if (line[0] == 'T') { /* T <mode> <n>: n LED ticks; each prints what the ring got, then E */
            unsigned m, n; sscanf(line + 2, "%u %u", &m, &n);
            while (n--) {
                TIMER += 1600000; main_poll(); TIMER += 1600000; main_poll(); /* two main-loop passes per LED tick */
                ring_tick(m, 0x180, (u8 *)0x3452);
                if (REGS[0x780] & 2) printf("W %u\n", REGS[0x798] | REGS[0x799] << 8);
                printf("E\n");
            }
            continue;
        }
        if (line[0] == 'C') { unsigned a, b; sscanf(line + 2, "%x %x", &a, &b); ring_command(a, b); continue; }
        if (line[0] == 'G') { printf("G %u %d\n", ring_level_now(), stock_passes); continue; }
        if (line[0] == 'A' || line[0] == 'Z') { /* vendor command hooks, by report bytes */
            u8 pk[8] = {0}; int n = 0; unsigned x;
            for (char *q = line + 2; n < 8 && sscanf(q, "%2x", &x) == 1; q += 2) pk[n++] = x;
            if (line[0] == 'A') vendor_a(pk); else vendor_b(pk);
            continue;
        }
        if (line[0] == 'W' || line[0] == 'Q') { /* W <flag> <n>: n rest_poll calls on zeroed registers; Q <n>: n more. Then the timer word and status */
            unsigned flag, n;
            if (line[0] == 'W') { sscanf(line + 2, "%x %u", &flag, &n); for (int i = 0; i < 0x1000; i++) REGS[i] = 0; REST_FLAG = flag; }
            else sscanf(line + 2, "%u", &n);
            while (n--) rest_poll();
            printf("WD %08x %02x\n", *(u32 *)(REGS + 0x620), REGS[0x623]);
            continue;
        }
        if (line[0] == 'V') { unsigned off, v; sscanf(line + 2, "%x %x", &off, &v); REGS[off] = v; continue; } /* poke a register */
        if (line[0] == 'R') { /* R <ATT write packet hex>: one rumble_write call, then "-" */
            u8 pk[64] = {0}; int n = 0; unsigned x;
            for (char *q = line + 2; n < 64 && sscanf(q, "%2x", &x) == 1; q += 2) pk[n++] = x;
            rumble_write(pk); printf("-\n"); continue;
        }
        if (sscanf(line, "%x %x %x %x %x %x %x", &b, &lx, &ly, &rx, &ry, &lt, &rt) != 7) return 1;
        BTN = b; LX = lx; LY = ly; RX = rx; RY = ry; LT = lt; RT = rt;
        notifies = afters = 0;
        dirty(); /* so a byte the packer forgets to set is not zero by luck */
        if (pack_xbox() != 7 || notifies != 1 || afters != 1) { printf("bad return or call count\n"); return 1; }
    }
    return 0;
}
"""


def report1_fields(desc):
    """(page, usage) -> (bit offset, bit size) for the non-constant fields of input report 1, and its length in bits."""
    g = dict(page=0, size=0, count=0, rid=0)
    usages, umin, fields, bits, i = [], None, {}, 0, 0
    while i < len(desc):
        p = desc[i]
        n = (0, 1, 2, 4)[p & 3]
        v = int.from_bytes(desc[i + 1:i + 1 + n], "little")
        kind, tag = p >> 2 & 3, p >> 4
        i += 1 + n
        if kind == 1:
            g[{0: "page", 7: "size", 8: "rid", 9: "count"}.get(tag, "_")] = v
        elif kind == 2:
            if tag == 0:
                usages.append((g["page"], v) if n < 4 else (v >> 16, v & 0xFFFF))
            elif tag == 1:
                umin = v
            elif tag == 2:
                usages += [(g["page"], u) for u in range(umin, v + 1)]
        elif kind == 0:
            if tag == 8 and g["rid"] == 1:  # Input
                for k in range(g["count"]):
                    if not v & 1:  # not constant
                        fields[usages[min(k, len(usages) - 1)]] = (bits, g["size"])
                    bits += g["size"]
            if tag in (8, 9, 0xB, 0xA):  # main items clear the local usages
                usages, umin = [], None
    return fields, bits


FIELDS, NBITS = report1_fields(bytes.fromhex(open(os.path.join(HERE, "report-map.hex")).read()))
LX, LY, RX, RY = (1, 0x30), (1, 0x31), (1, 0x32), (1, 0x35)
LT, RT, HAT, SHARE = (2, 0xC5), (2, 0xC4), (1, 0x39), (0xC, 0xB2)  # Brake = left trigger, Accelerator = right
# The 2C's button word, named after the stock 360 converter (0xebfe) that maps it to 360 buttons.
WORD = {13: "A", 12: "B", 4: "X", 5: "Y", 10: "LB", 11: "RB", 3: "View", 0: "Menu", 17: "Xbox", 1: "LS", 2: "RS"}
# Xbox report 1 button numbers (Button page; names from SDL and xpadneo).
XBOX = {"A": 1, "B": 2, "X": 4, "Y": 5, "LB": 7, "RB": 8, "View": 11, "Menu": 12, "Xbox": 13, "LS": 14, "RS": 15}
UP, RIGHT, DOWN, LEFT = 9, 6, 8, 7


def stock_hat(b):
    """The stock BLE packer's d-pad decision (0xb9de-0xbab6), as 2C hat 0-7 or None."""
    on = lambda *bits: all(b >> x & 1 for x in bits)
    for bits, h in (((UP, RIGHT), 1), ((DOWN, RIGHT), 3), ((DOWN, LEFT), 5), ((UP, LEFT), 7),
                    ((UP,), 0), ((RIGHT,), 2), ((DOWN,), 4), ((LEFT,), 6)):
        if on(*bits):
            return h
    return None


def model(b, lx, ly, rx, ry, lt, rt):
    """Expected value of every report-1 field."""
    hid_x = lambda raw: (0x7FFF - raw + 0x8000) & 0xFFFF  # 360 converter: 0x7fff - raw is + right; HID 0 = left
    hid_y = lambda raw: (0x7FFF - (0x7FFF - raw)) & 0xFFFF  # 360 converter: 0x7fff - raw is + up; HID 0 = up
    h = stock_hat(b)
    want = {LX: hid_x(lx), LY: hid_y(ly), RX: hid_x(rx), RY: hid_y(ry), LT: (lt & 0xFF) * 1023 / 255,
            RT: (rt & 0xFF) * 1023 / 255, HAT: 0 if h is None else h + 1, SHARE: 0}  # Xbox hat: 1 = N ... 8 = NW
    pressed = {XBOX[name] for bit, name in WORD.items() if b >> bit & 1}
    want.update({(9, n): int(n in pressed) for n in range(1, 16)})
    return want


def check(v, report):
    if len(report) * 8 != NBITS:
        return "length"
    num = int.from_bytes(report, "little")
    got = {f: num >> off & (1 << size) - 1 for f, (off, size) in FIELDS.items()}
    used = sum(((1 << size) - 1) << off for off, size in FIELDS.values())
    if num & ~used:
        return "padding bits set"
    for f, w in model(*v).items():
        if f in (LT, RT):  # u8 -> u10: within 1 of exact, and exact at 0 and 255
            raw = (v[5] if f == LT else v[6]) & 0xFF
            if abs(got[f] - w) >= 1 or (raw in (0, 255) and got[f] != w):
                return f"trigger {f}: {got[f]} for {raw}"
        elif got[f] != w:
            return f"field {f}: {got[f]:#x}, want {w:#x}"


RUMBLE_CAP = 255


def rumble_packet(value):
    """Telink ATT write as rumble_write sees it: type, rf_len, L2CAP length, channel 4, opcode 0x52, handle 0x21."""
    return bytes([2, 7 + len(value)]) + (3 + len(value)).to_bytes(2, "little") + b"\x04\x00\x52\x21\x00" + value


SRC = [os.path.join(HERE, f) for f in ("packer.c", "settings.c", "rest.c")]


def _run_harness(stdin, cflags=()):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "h.c"), "w").write(HARNESS)
        exe = os.path.join(d, "t")
        subprocess.run(["cc", "-DHOST", "-O1", *cflags, "-o", exe, *SRC, os.path.join(d, "h.c")], check=True)
        return subprocess.run([exe], input=stdin, capture_output=True, text=True).stdout


def rumble_check():
    """Each rumble report -> the expected motor_set call (Xbox report 3: mask, LT, RT, strong, weak, duration, delay, loop)."""
    rnd = random.Random(2)
    cases = [bytes([0x0F, 0, 0, s, w, 0xFF, 0, 0xEB]) for s, w in ((0, 0), (100, 100), (30, 29), (31, 0), (0, 31), (255, 255))]
    cases += [bytes([m, 50, 50, 80, 20, 0xFF, 0, 0]) for m in range(16)]
    cases += [rnd.randbytes(8) for _ in range(50)] + [bytes([0x0F, 0, 0, 90, 90, 0]), bytes([0x0F, 0, 0, 90, 90])]
    def want(v):
        if len(v) < 6 or v[0] & 0x80:  # too short, or a Home ring command
            return "-"
        s, w = (v[3] if v[0] & 2 else 0), (v[4] if v[0] & 1 else 0)
        lvl = lambda m: min(m * 5 // 2, RUMBLE_CAP)  # Xbox 0-100 -> the 360's 0-255 that f93c expects
        return f"M {lvl(s)} {lvl(w)} {v[5] or 1} -"  # hold = Xbox duration (10 ms), 1 for none
    raw = _run_harness("".join("R " + rumble_packet(v).hex() + "\n" for v in cases)).splitlines()
    got, cur = [], []
    for line in raw:  # each call prints its motor_set lines, then "-"
        cur.append(line)
        if line == "-":
            got.append(" ".join(cur)); cur = []
    return [(("rumble", v.hex()), g, f"want {want(v)}") for v, g in zip(cases, got) if g != want(v)] + \
        ([] if len(got) == len(cases) else [(("rumble",), str(len(got)), f"{len(cases)} calls")])


def ring_check():
    """ring_tick against the Telink B80 PWM1 and PB7 registers (bits of each that must not change are checked with both fills)."""
    cases = [(m, lv, f) for m in (0, 1, 2, 3) for lv in (0, 1, 10, 250) for f in (0, 0xFF)]
    # one ring_tick call per case, from fresh state; with the fill in the registers, PD0 reads as set when f is 0xFF
    out = _run_harness("".join("L %x %x %x\n" % c for c in cases)).splitlines()
    bad, i = [], 0
    for m, lv, f in cases:
        on = m == 1 and lv != 0
        want = []
        if not on:
            want.append("D %x 180 3452" % (0 if m == 1 else m))
        if on:
            regs = (f | 2, f & ~2, f & ~2, f & ~8, f & ~0x80, 4, f & ~0x80)
            word = 1000 << 16 | lv
        else:
            regs = (f & ~2, f, f, f, f, f, f | 0x80)
            word = f * 0x01010101
        want.append(" ".join("%02x" % (r & 0xFF) for r in regs) + " %08x" % word)
        got = out[i:i + len(want)]
        i += len(want)
        if got != want:
            bad.append((("ring", m, lv, f), " | ".join(got), f"want {' | '.join(want)}"))
    return bad


L4, R4 = 1 << 26, 1 << 25
NORMAL = 0xFFFF
STRONG, SHORT, LONG = 200, 20, 50


class Sim:
    """A script for the harness. Levels by PWM compare value, in the order Normal, 25, 5, 1, 0.1 %, off."""

    def __init__(self, level=50, saved=0xFF, alerts=1, pct=50, ext=0, full=0):
        self.lines = [f"I {level:x} {saved:x} {alerts} {pct} {ext} {full}"]

    def add(self, *lines):
        self.lines += lines
        return self

    def btn(self, b): return self.add(f"B {b:x}")
    def poll(self, n=1): return self.add(f"P {n}")
    def tick(self, n=1, mode=1): return self.add(f"T {mode} {n}")
    def bat(self, pct, ext=0, full=0): return self.add(f"X {pct} {ext} {full}")
    def press(self, b): return self.btn(b).poll(2).btn(0).poll(2)
    def out(self): return _run_harness("".join(x + "\n" for x in self.lines)).splitlines()

    def ticks(self):
        """What each tick did, as lists of lines."""
        out, cur = [], []
        for line in self.out():
            if line == "E":
                out.append(cur); cur = []
            else:
                cur.append(line)
        return out


def lit(t):
    """Whether the ring is on in one tick's output."""
    return any(x.startswith("W ") or x.startswith("D 1 ") for x in t)


def duty(t):
    return next((int(x[2:]) for x in t if x.startswith("W ")), None)


def motors(ticks):
    """The pulses started in these ticks, as (tick, hold)."""
    return [(i, int(x.split()[3])) for i, t in enumerate(ticks) for x in t if x.startswith("M ") and x.split()[1] != "0"]


def level_of(sim):
    return int([x for x in sim.add("G").out() if x.startswith("G ")][-1].split()[1])


def test_saved_level_wins_over_installed():
    assert duty(Sim(level=50, saved=0x21 ).tick().ticks()[0]) == 250  # saved 25 % while 5 % (index 2) was installed


def test_a_bad_saved_level_is_ignored():
    for saved in (0xFF, 0x2F, 0x26, 0x27):
        assert duty(Sim(level=50, saved=saved).tick().ticks()[0]) == 50, hex(saved)


def test_installing_another_level_wins_over_a_saved_one():
    assert duty(Sim(level=10, saved=0x21).tick().ticks()[0]) == 10  # saved under 5 %, and now 1 % is installed


def test_chord_moves_one_level_per_press():
    s = Sim(level=250).tick().btn(L4 | R4).poll(50).tick(3).btn(0).poll(2).tick()
    assert duty(s.ticks()[-1]) == 50


def test_chord_works_with_either_button_first():
    assert duty(Sim(level=250).tick().btn(L4).poll(2).btn(L4 | R4).poll(2).btn(0).poll(2).tick().ticks()[-1]) == 50
    assert duty(Sim(level=250).tick().btn(R4).poll(2).btn(L4 | R4).poll(2).btn(0).poll(2).tick().ticks()[-1]) == 50


def test_chord_reads_the_physical_word():
    s = Sim(level=50).tick().add("Y 0").add(f"K {1 << 26 | 1 << 25:x}").tick()
    assert duty(s.ticks()[-1]) != 50  # stock clears a mapped paddle's bit in the other word
    s = Sim(level=50).tick().add(f"Y {1 << 26 | 1 << 25:x}").add("K 0").tick()
    assert duty(s.ticks()[-1]) == 50  # and a mapped button pressing them isn't a chord


def test_chord_needs_both_buttons():
    for b in (L4, R4):
        assert duty(Sim(level=250).tick().press(b).tick().ticks()[-1]) == 250


def test_a_tap_between_ticks_counts():
    assert duty(Sim(level=250).tick().btn(L4 | R4).poll(1).btn(0).poll(1).tick().ticks()[-1]) == 50


def test_chord_wraps_around():
    s = Sim(level=NORMAL).tick()
    seen = []
    for _ in range(6):
        s = s.press(L4 | R4).tick()
    for t in s.ticks():
        seen.append(duty(t) if duty(t) is not None else ("normal" if lit(t) else "off"))
    assert seen == ["normal", 250, 50, 10, 1, "off", "normal"], seen


def test_several_presses_make_one_save():
    s = Sim(level=NORMAL).tick()
    for _ in range(3):
        s = s.press(L4 | R4).tick(5)
    s.tick(20)
    saves = [x for x in s.out() if x.startswith("SAVE")]
    assert saves == ["SAVE 03"], saves  # installed Normal (index 0), now 1 % (index 3)


def test_a_save_comes_three_seconds_after_the_last_press():
    ticks = Sim(level=NORMAL).tick().press(L4 | R4).tick(20).ticks()
    assert [i for i, t in enumerate(ticks) if any(x.startswith("SAVE") for x in t)] == [15]


def test_the_firmwares_own_chord_check_keeps_running():
    out = Sim().poll(7).add("G").out()
    assert out[-1].split()[2] == "7", out[-1]


def test_charging_blinks_slowly():
    ticks = Sim(ext=1).tick(20).ticks()
    assert [lit(t) for t in ticks] == ([True] * 5 + [False] * 5) * 2


def test_low_battery_blinks_fast():
    ticks = Sim(pct=15).tick(30).ticks()[20:]
    assert [lit(a) != lit(b) for a, b in zip(ticks, ticks[1:])] == [True] * 9


def test_battery_above_the_limit_stays_steady():
    assert all(lit(t) for t in Sim(pct=16).tick(30).ticks())


def test_a_charged_controller_is_steady():
    assert all(lit(t) for t in Sim(ext=1, full=1).tick(30).ticks())


def test_pairing_blink_takes_priority():
    for t in Sim(pct=4).tick(30, mode=2).ticks():
        assert any(x.startswith("D 2 ") for x in t) and duty(t) is None


def test_off_level_still_alerts():
    ticks = Sim(level=0, ext=1).tick(10).ticks()
    assert [duty(t) for t in ticks[:5]] == [10] * 5 and not any(lit(t) for t in ticks[5:])
    assert not any(lit(t) for t in Sim(level=0).tick(30).ticks())


def test_normal_alerts_at_full_brightness():
    ticks = Sim(level=NORMAL, ext=1).tick(10).ticks()
    assert all(any(x.startswith("D 1 ") for x in t) for t in ticks[:5])


def test_charging_shows_with_the_controller_off():
    assert [lit(t) for t in Sim(ext=1).tick(10, mode=0).ticks()] == [True] * 5 + [False] * 5
    assert not any(lit(t) for t in Sim(pct=4).tick(30, mode=0).ticks())


def test_without_the_alerts_tweak_nothing_blinks_or_vibrates():
    ticks = Sim(alerts=0, pct=4).tick(30).bat(4, 1).tick(30).ticks()
    assert all(lit(t) for t in ticks) and not motors(ticks)


def test_alert_state_has_hysteresis():
    s = Sim(pct=50).tick(20).bat(15).tick(4).bat(17).tick(10)
    t = s.ticks()[24:]
    assert any(lit(a) != lit(b) for a, b in zip(t, t[1:])), "still low at 17 %"
    t = Sim(pct=50).tick(20).bat(15).tick(4).bat(18).tick(10).ticks()[24:]
    assert all(lit(x) for x in t), "clears at 18 %"
    assert len(motors(Sim(pct=50).tick(20).bat(5).tick(10).bat(6).tick(10).ticks())) == 2, "very low stays at 6 %"
    assert len(motors(Sim(pct=50).tick(20).bat(5).tick(10).bat(7).tick(10).bat(5).tick(10).ticks())) == 4, "clears at 7 %"


def test_pulses_on_reaching_5_percent_then_every_5_minutes():
    m = motors(Sim(pct=50).tick(20).bat(5).tick(1510).ticks())
    assert [h for _, h in m] == [SHORT] * 4, m
    assert m[2][0] - m[0][0] == 1500, m


def test_two_short_pulses_are_as_tried_on_the_controller():
    m = motors(Sim(pct=50).tick(20).bat(5).tick(10).ticks())
    assert m[1][0] - m[0][0] == 4, m  # 800 ms from start to start


def stops(ticks):
    return [i for i, t in enumerate(ticks) if "M 0 0 1" in t]


def test_pulses_last_as_long_as_chosen_on_any_connection():
    ticks = Sim().tick(20).bat(50, 1).tick(5).ticks()
    assert stops(ticks)[0] - motors(ticks)[0][0] == 1, ticks[20:]  # 200 ms: stopped in the next tick's passes
    lines = Sim().tick(20).bat(50, 1).tick(160).bat(100, 1, 1).tick(1).add("P 4", "G").out()
    assert "M 0 0 1" not in lines[lines.index(f"M {STRONG} {STRONG} {LONG}"):lines.index(f"M {STRONG} {STRONG} {LONG}") + 2]
    long_start = Sim().tick(20).bat(50, 1).tick(160).bat(100, 1, 1).tick(5).ticks()
    assert stops(long_start)[-1] - motors(long_start)[-1][0] == 3, "500 ms ends in the third tick's passes"


def test_a_level_saved_under_another_install_is_cleared_once():
    saves = [x for x in Sim(level=10, saved=0x21).tick(5).out() if x.startswith("SAVE")]
    assert saves == ["SAVE 33"], saves  # now 1 % (index 3), installed and current


def test_going_back_to_the_first_level_doesnt_bring_the_old_save_back():
    assert not [x for x in Sim(level=50, saved=0x33).tick().out() if x.startswith("SAVE 23")]
    assert duty(Sim(level=50, saved=0x33).tick().ticks()[0]) == 50


def test_no_save_at_startup_without_reason():
    for saved in (0xFF, 0x21, 0x22):
        assert not [x for x in Sim(level=50, saved=saved).tick(5).out() if x.startswith("SAVE")], hex(saved)


def test_no_low_battery_pulses_on_external_power():
    m = motors(Sim(pct=50, ext=1).tick(20).bat(4, 1).tick(1600).ticks())
    assert not m, m


def test_one_short_pulse_when_charging_starts():
    m = motors(Sim().tick(20).bat(50, 1).tick(10).ticks())
    assert [h for _, h in m] == [SHORT], m


def test_one_long_pulse_when_charging_completes():
    m = motors(Sim().tick(20).bat(50, 1).tick(160).bat(100, 1, 1).tick(10).ticks())
    assert [h for _, h in m] == [SHORT, LONG], m


def test_pulses_use_both_motors_at_the_chosen_strength():
    out = Sim().tick(20).bat(50, 1).tick(1).out()
    assert f"M {STRONG} {STRONG} {SHORT}" in out, out


def test_starting_up_while_plugged_in_gives_no_pulse():
    assert not motors(Sim(ext=1).tick(10).bat(100, 1, 1).tick(10).ticks())


def test_a_wobbling_charge_state_pulses_once_until_unplugged():
    s = Sim().tick(20).bat(50, 1).tick(160)
    for _ in range(4):
        s = s.bat(100, 1, 1).tick(5).bat(100, 1, 0).tick(5)
    assert [h for _, h in motors(s.ticks())] == [SHORT, LONG]
    assert [h for _, h in motors(s.bat(100, 0).tick(5).bat(100, 1).tick(160).bat(100, 1, 1).tick(5).ticks())] == [SHORT, LONG, SHORT, LONG]


def test_unplugging_gives_no_pulse():
    assert [h for _, h in motors(Sim().tick(20).bat(50, 1).tick(10).bat(50, 0).tick(10).ticks())] == [SHORT]


def test_a_low_reading_right_after_starting_doesnt_alert():
    ticks = Sim(pct=0).tick(10).ticks()
    assert all(lit(t) for t in ticks) and not motors(ticks)


def marked(level, save):
    return "R " + rumble_packet(bytes([0x80, level, save, 0, 0, 0, 0, 0])).hex()


def test_marked_report_sets_the_level():
    assert duty(Sim(level=50).tick().add(marked(1, 0)).tick().ticks()[-1]) == 250


def test_marked_report_can_save():
    out = Sim(level=50).tick().add(marked(1, 1)).tick(2).out()
    assert "SAVE 21" in out, out


def test_marked_report_doesnt_touch_the_motors():
    assert not [x for x in Sim().tick().add(marked(1, 0)).out() if x.startswith("M ")]


def test_an_unknown_level_is_ignored():
    for level in (6, 0x7F, 0xFF):
        assert duty(Sim(level=50).tick().add(marked(level, 0)).tick().ticks()[-1]) == 50


def test_settings_are_loaded_once_and_commands_reach_them():
    out = Sim(level=50).tick().add("A 81050055").tick(2).out()
    assert out.count("WRITE 7a000") == 1 and out.count("ERASE 7a000") == 1, out


def test_rumble_without_the_tail_still_works():
    out = Sim().add("N", "R " + rumble_packet(bytes([3, 0, 0, 40, 20, 9, 0, 0])).hex()).out()
    assert "M 100 50 9" in out, out


def test_marked_report_does_nothing_without_the_ring_code():
    out = Sim(level=50).tick().add("N", marked(1, 1)).tick(2).ticks()
    assert duty(out[-1]) == 50 and not any(x.startswith("SAVE") for t in out for x in t)


def test_cable_command_sets_the_level():
    for hook, stock in (("A", "VA"), ("Z", "VB")):
        out = Sim(level=50).tick().add(f"{hook} 8105005201").tick().out()
        assert stock in out and "W 250" in out, (hook, out)


def test_cable_command_saves():
    assert "SAVE 22" in Sim(level=50).tick().add("A 81050053").tick(2).out()


def test_other_vendor_commands_only_reach_the_firmware():
    for cmd in ("8105005101", "8105002101", "8205005201", "8104005201", "8105015201"):
        out = Sim(level=50).tick().add(f"A {cmd}").tick().out()
        assert "W 250" not in out and "VA" in out and not any(x.startswith("SAVE") for x in out), cmd


def watchdog(*lines, cflags=()):
    """The timer word at 0x620 and the status byte at 0x623 after each W or Q line."""
    out = _run_harness("".join(x + "\n" for x in lines), cflags).splitlines()
    return [tuple(int(v, 16) for v in x.split()[1:]) for x in out if x.startswith("WD ")]


def test_watchdog_arms_once_with_3_s():
    w, feed = watchdog("W 1 1")[0]
    assert (w >> 9 & 0x3FFF, bool(w & 1 << 6), bool(w & 1 << 23), feed) == (549, True, True, 8), hex(w)
    w, feed = watchdog("W 1 1", "V 620 45", "V 621 00", "Q 1")[-1]  # armed: the word isn't written again, only fed
    assert (w & 0xFF, w >> 9 & 0x3FFF != 549, feed) == (0x45, True, 8), hex(w)


def test_watchdog_off_without_the_flag():
    for flag in (0, 0xFF):
        assert watchdog(f"W {flag:x} 3") == [(0, 0)], flag


def test_watchdog_rearms_after_being_turned_off():
    w, feed = watchdog("W 1 1", "V 622 00", "Q 1")[-1]
    assert (w >> 9 & 0x3FFF, bool(w & 1 << 23), feed) == (549, True, 8), hex(w)


RING_TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def settings_check():
    """firmware-src/test_settings.c: the settings code's own tests, in C. Each failure is one line."""
    with tempfile.TemporaryDirectory() as d:
        exe = os.path.join(d, "s")
        subprocess.run(["cc", "-DHOST", "-O1", "-o", exe, os.path.join(HERE, "settings.c"), os.path.join(HERE, "test_settings.c")], check=True)
        run = subprocess.run([exe], capture_output=True, text=True)
    return [] if run.returncode == 0 else [(("settings",), run.stdout, "failed")]


def ring_logic_check():
    bad = []
    for t in RING_TESTS:
        try:
            t()
        except AssertionError as e:
            bad.append(((t.__name__,), str(e)[:300], "failed"))
    return bad


def main():
    assert set(FIELDS) == {LX, LY, RX, RY, LT, RT, HAT, SHARE} | {(9, n) for n in range(1, 16)}, sorted(FIELDS)
    rnd = random.Random(1)
    c = 0x7FFF
    vec = [(0, c, c, c, c, 0, 0)]
    vec += [(1 << bit, c, c, c, c, 0, 0) for bit in range(32)]
    vec += [(sum(1 << x for i, x in enumerate((UP, RIGHT, DOWN, LEFT)) if m >> i & 1), 0, 0xFFFF, 0x1234, 0xFEDC, 0, 0)
            for m in range(16)]
    vec += [(0, s, s, s, s, 0, 0) for s in (0, 1, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF)]
    vec += [(0, c, c, c, c, a, b) for a, b in itertools.product((0, 1, 63, 64, 128, 254, 255, 0x1FF, 0xFF00), repeat=2)]
    vec += [(rnd.getrandbits(32), *(rnd.getrandbits(16) for _ in range(6))) for _ in range(300)]
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "h.c"), "w").write(HARNESS)
        exe = os.path.join(d, "t")
        subprocess.run(["cc", "-DHOST", "-O1", "-o", exe, *SRC, os.path.join(d, "h.c")], check=True)
        run = subprocess.run([exe], input="".join("%x %x %x %x %x %x %x\n" % v for v in vec), capture_output=True, text=True)
        out = run.stdout.split()
        if run.returncode:
            sys.exit(f"FAIL: harness stopped after {len(out) - 1} reports: {run.stdout.splitlines()[-1]}")
    bad = [(v, o, why) for v, o in zip(vec, out) for why in [check(v, bytes.fromhex(o))] if why]
    bad += rumble_check() + ring_check() + ring_logic_check() + settings_check()
    if len(out) != len(vec) or bad:
        for v, o, why in bad[:10]:
            print("input", [hex(x) if isinstance(x, int) else x for x in v], "got", o, "->", why)
        sys.exit(f"FAIL: {len(bad)} of {len(vec)} wrong ({len(out)} outputs)")
    print(f"ok: {len(vec)} vectors, every field of report 1 as parsed from report-map.hex; rumble_write as modelled; {len(RING_TESTS)} ring checks")


if __name__ == "__main__":
    main()
