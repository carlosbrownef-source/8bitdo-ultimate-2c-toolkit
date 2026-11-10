# SPDX-License-Identifier: GPL-3.0-or-later
"""Simulated devices that answer like the controller's firmware and bootloader, for tests and U2C_SIM=1 UI checks."""
import time

from . import settings as settings_record
from .protocol.boot import crc16


class SimApp:
    """The update channel of a running controller (report ID 0x81 out, 0x02 in)."""

    def __init__(self, flash: bytes, needs_session=False, needs_unprotect=False):
        self.flash, self.open, self.unprot, self.sent = bytes(flash), not needs_session, needs_unprotect, []
        self.drop_saves, self.mapping, self.dead_zone_off, self.reloading_until = False, {}, None, 0.0
        kept = settings_record.parse(self.flash[settings_record.SECTOR:settings_record.SECTOR + settings_record.SIZE]) if len(self.flash) > 0x7A000 else None
        self.fields = [(kept or settings_record.DEFAULTS)[f.name] for f in settings_record.FIELDS]  # the settings in its RAM

    def xfer(self, req: bytes, timeout: float = 0.5, accept=None):
        self.sent.append(req[:5].hex())
        if req[0:2] != b"\x81\x05" or req[2:4] == b"\x00\x51":
            raise AssertionError(f"unexpected request {req[:5].hex()}")
        if req[2] == 0x00:
            return self._short_command(req)
        if req[2] == 0xC1:
            self.open = True
            return bytes([0x02, 0x05]).ljust(64, b"\0")
        if req[2] != 0x05 or not self.open:
            return None
        n, a = int.from_bytes(req[6:8], "little"), int.from_bytes(req[14:18], "little")
        hdr = bytearray(req[2:18])
        hdr[2:4], hdr[0], hdr[1] = hdr[0:2], 0, 0
        return (b"\x02\x05" + bytes(hdr) + self.flash[a:a + n]).ljust(64, b"\0")

    def _short_command(self, req: bytes):
        cmd = req[3]
        if 0x54 <= cmd <= 0x58 and time.monotonic() < self.reloading_until:
            return None   # settings.c ignores them until its next 100 ms pass has read the record again
        if cmd == 0x21:
            self.open = not self.unprot
            return bytes([0x02, 0x22]).ljust(64, b"\0")
        if cmd == 0x54:
            fields = settings_record.FIELDS
            if req[4] < len(fields) and settings_record.valid(fields[req[4]].name, req[5]):
                self.fields[req[4]] = req[5]
        elif cmd == 0x56:
            self.fields = [f.default for f in settings_record.FIELDS]
            self.mapping, self.dead_zone_off = {0: 0, 1: 0}, 0
        elif cmd == 0x5A:
            kept = settings_record.parse(self.flash[settings_record.SECTOR:settings_record.SECTOR + settings_record.SIZE])
            self.fields = [(kept or settings_record.DEFAULTS)[f.name] for f in settings_record.FIELDS]
            self.reloading_until = time.monotonic() + 0.1
        elif cmd == 0x57:
            self.mapping[req[4]] = int.from_bytes(req[5:9], "little")
        elif cmd == 0x58:
            self.dead_zone_off = req[4]
        elif cmd not in (0x52, 0x53, 0x55):
            raise AssertionError(f"unexpected request {req[:5].hex()}")
        if cmd in (0x55, 0x56) and not self.drop_saves:
            raw = settings_record.encode({f.name: v for f, v in zip(settings_record.FIELDS, self.fields)})
            self.flash = self.flash[:settings_record.SECTOR] + raw + self.flash[settings_record.SECTOR + len(raw):]
            stock = bytearray(self.flash[0x73000:0x7301A])
            if self.dead_zone_off is not None:
                stock[6] = self.dead_zone_off
            for slot, at in ((0, 17), (1, 21)):
                if slot in self.mapping:
                    stock[at:at + 4] = self.mapping[slot].to_bytes(4, "little")
            self.flash = self.flash[:0x73000] + bytes(stock) + self.flash[0x7301A:]
        return None

    def close(self):
        pass


class SimBoot:
    """The bootloader (2dc8:3208): 64-byte reports without report ID; the dongle's flash aliases above its size."""

    def __init__(self, flash: bytes, fail_after=None, identity="auto"):
        self.f, self.size, self.ops, self.params, self.fail_after = bytearray(flash), len(flash), [], [], fail_after
        self.identity = (0x301B if len(flash) > 0x20000 else 0x301C) if identity == "auto" else identity  # None: no answer

    def xfer(self, r: bytes, timeout: float = 0.5, accept=None):
        cmd, n = int.from_bytes(r[1:3], "little"), int.from_bytes(r[5:7], "little")
        crc, param, addr = int.from_bytes(r[7:9], "little"), int.from_bytes(r[9:13], "little"), int.from_bytes(r[13:17], "little")
        ok = lambda extra=b"": (bytes([0, 5, 0, 0]) + r[1:3] + r[5:17] + extra).ljust(64, b"\0")   # as 0x3804 builds it
        if cmd == 5:
            return ok(bytes(self.f[(addr + i) % self.size] for i in range(param)))
        if cmd == 8:
            if self.identity is None:
                return None
            a = bytearray(ok(self.identity.to_bytes(2, "little")))
            a[6:8] = b"\x02\0"
            return bytes(a)
        if self.fail_after is not None and len(self.ops) >= self.fail_after:
            return None  # unplugged
        if cmd == 4:
            lo, hi = addr // 0x1000 * 0x1000, (addr + param + 0xFFF) // 0x1000 * 0x1000
            self.ops.append(("erase", lo, hi))
            self.f[lo:hi] = b"\xff" * (hi - lo)
            return ok()
        if cmd == 3:
            data = r[17:17 + n]
            if crc16(data) != crc:
                return (bytes([0, 5, 1, 0]) + r[1:3] + r[5:17]).ljust(64, b"\0")
            self.ops.append(("write", addr, addr + n))
            self.params.append(param)
            for i, x in enumerate(data):
                self.f[addr + i] &= x  # flash only clears bits
            return ok()
        raise AssertionError(f"unexpected bootloader command {cmd}")

    def close(self):
        pass


def install(store, unknown: bool = False) -> None:
    """U2C_SIM=1: pretend a controller in boot mode is plugged in, backed by a synthetic flash and a synthetic 'stock'
    (with matching constants), so the UI can be exercised without hardware. Seeds a backup of that flash in the store.
    unknown=True: the simulated controller has damaged banks A and B and a blank update record (version undeterminable)."""
    import hashlib
    import random
    from pathlib import Path

    from . import cli
    from .firmware import image, recipes
    from .transport import DeviceInfo
    from .ops import devices

    rnd = random.Random(1)
    stock = bytearray(rnd.randbytes(image.BANK_A_SIZE))
    stock[0x18274 - image.BASE:] = bytes(image.BANK_A_END - 0x18274)
    stock = bytes(stock)
    flash = bytearray(b"\xff" * image.FLASH_SIZE)
    flash[0:0x5000] = rnd.randbytes(0x5000)
    flash[image.BASE:image.BANK_A_END] = stock
    for a in range(image.CONFIG_START, image.FLASH_SIZE, 0x1000):
        flash[a:a + 64] = rnd.randbytes(64)
    whole = recipes.whole(stock)
    consts = (hashlib.sha256(stock).hexdigest(),
              {(e.addr, e.size): hashlib.sha256(whole[e.addr - image.BASE:e.addr - image.BASE + e.size]).hexdigest()
               for r in recipes.RECIPES.values() for e in r.edits},
              hashlib.sha256(recipes.masked(whole)).hexdigest())
    recipes._constants = lambda a=None, b=None, c=None: consts
    Path(store).mkdir(parents=True, exist_ok=True)
    (Path(store) / "controller-sim.bin").write_bytes(bytes(flash))
    live = bytearray(flash)
    if unknown:
        live[image.BASE:image.BANK_A_END] = rnd.randbytes(image.BANK_A_SIZE)
        live[0x40000:0x40000 + image.BANK_A_SIZE] = rnd.randbytes(image.BANK_A_SIZE)
        live[0x3F000:0x3F034] = b"\xff" * 0x34
    dev = SimBoot(bytes(live))
    info = DeviceInfo(0x2DC8, 0x3208, 0x8C, "USB", "Simulated controller (boot mode)", None)
    cli.find = lambda: [devices.Found(info, "boot")]
    cli.open_channel = lambda i, rid: dev
    cli.fetch.fetch_stock = lambda: stock
