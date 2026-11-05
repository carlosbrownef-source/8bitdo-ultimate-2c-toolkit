#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native test of packer.c: compile it for the Mac (-DHOST), feed input vectors, and check each report field by field
against a model. The field layout is parsed from report-map.hex; the meaning of the 2C's state comes from the stock
firmware (360 converter, stock packer), not from the C. The TC32 build itself is checked by patch.py."""
import itertools, os, random, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = r"""
#include <stdio.h>
#include <stdlib.h>
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32;
u32 BTN; u16 LX, LY, RX, RY, LT, RT;
u8 REGS[0x1000] __attribute__((aligned(4))); volatile u16 RING_LEVEL;
static int notifies, afters;
int pack_xbox(void);
int rumble_write(u8 *p);
void ring_led(u32 mode, u32 pin, u8 *counter);
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
        if (line[0] == 'L') { /* L <mode> <level> <fill>: one ring_led call on registers all set to fill, then their state */
            unsigned mode, level, fill;
            sscanf(line + 2, "%x %x %x", &mode, &level, &fill);
            for (int i = 0; i < 0x1000; i++) REGS[i] = fill;
            RING_LEVEL = level;
            ring_led(mode, 0x180, (u8 *)0x3452);
            printf("%02x %02x %02x %02x %02x %02x %02x %02x%02x%02x%02x\n", REGS[0x780], REGS[0x784], REGS[0x786], REGS[0x7b0], REGS[0x50b], REGS[0x557], REGS[0x50e],
                   REGS[0x79b], REGS[0x79a], REGS[0x799], REGS[0x798]);
            continue;
        }
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


def _run_harness(stdin):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "h.c"), "w").write(HARNESS)
        exe = os.path.join(d, "t")
        subprocess.run(["cc", "-DHOST", "-O1", "-o", exe, os.path.join(HERE, "packer.c"), os.path.join(d, "h.c")], check=True)
        return subprocess.run([exe], input=stdin, capture_output=True, text=True).stdout


def rumble_check():
    """Each rumble report -> the expected motor_set call (Xbox report 3: mask, LT, RT, strong, weak, duration, delay, loop)."""
    rnd = random.Random(2)
    cases = [bytes([0x0F, 0, 0, s, w, 0xFF, 0, 0xEB]) for s, w in ((0, 0), (100, 100), (30, 29), (31, 0), (0, 31), (255, 255))]
    cases += [bytes([m, 50, 50, 80, 20, 0xFF, 0, 0]) for m in range(16)]
    cases += [rnd.randbytes(8) for _ in range(50)] + [bytes([0x0F, 0, 0, 90, 90, 0]), bytes([0x0F, 0, 0, 90, 90])]
    def want(v):
        if len(v) < 6:
            return "-"
        s, w = (v[3] if v[0] & 2 else 0), (v[4] if v[0] & 1 else 0)
        lvl = lambda m: min(m * 5 // 2, RUMBLE_CAP)  # Xbox 0-100 -> the 360's 0-255 that f93c expects
        return f"M {lvl(s)} {lvl(w)} {v[5] or 1} -"  # hold = Xbox duration (10 ms), 1 for none
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "h.c"), "w").write(HARNESS)
        exe = os.path.join(d, "t")
        subprocess.run(["cc", "-DHOST", "-O1", "-o", exe, os.path.join(HERE, "packer.c"), os.path.join(d, "h.c")], check=True)
        raw = subprocess.run([exe], input="".join("R " + rumble_packet(v).hex() + "\n" for v in cases),
                             capture_output=True, text=True).stdout.splitlines()
    got, cur = [], []
    for line in raw:  # each call prints its motor_set lines, then "-"
        cur.append(line)
        if line == "-":
            got.append(" ".join(cur)); cur = []
    return [(("rumble", v.hex()), g, f"want {want(v)}") for v, g in zip(cases, got) if g != want(v)] + \
        ([] if len(got) == len(cases) else [(("rumble",), str(len(got)), f"{len(cases)} calls")])


def ring_check():
    """ring_led against the Telink B80 PWM1 and PB7 registers (bits of each that must not change are checked with both fills)."""
    cases = [(m, lv, f) for m in (0, 1, 2, 3) for lv in (0, 1, 10, 250) for f in (0, 0xFF)]
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
        subprocess.run(["cc", "-DHOST", "-O1", "-o", exe, os.path.join(HERE, "packer.c"), os.path.join(d, "h.c")], check=True)
        run = subprocess.run([exe], input="".join("%x %x %x %x %x %x %x\n" % v for v in vec), capture_output=True, text=True)
        out = run.stdout.split()
        if run.returncode:
            sys.exit(f"FAIL: harness stopped after {len(out) - 1} reports: {run.stdout.splitlines()[-1]}")
    bad = [(v, o, why) for v, o in zip(vec, out) for why in [check(v, bytes.fromhex(o))] if why]
    bad += rumble_check() + ring_check()
    if len(out) != len(vec) or bad:
        for v, o, why in bad[:10]:
            print("input", [hex(x) if isinstance(x, int) else x for x in v], "got", o, "->", why)
        sys.exit(f"FAIL: {len(bad)} of {len(vec)} wrong ({len(out)} outputs)")
    print(f"ok: {len(vec)} vectors, every field of report 1 as parsed from report-map.hex; rumble_write as modelled")


if __name__ == "__main__":
    main()
