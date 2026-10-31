# SPDX-License-Identifier: GPL-3.0-or-later
"""Layout of the controller's flash (firmware 1.09) and the hash that identifies stock."""

FLASH_SIZE = 0x80000
BOOT_END = 0x6000              # bootloader 0x0-0x6000: never written
BASE = 0x6000                  # bank A, the running app
BANK_A_SIZE = 0x12400          # the v1.09 payload
BANK_A_END = BASE + BANK_A_SIZE
BANK_A_ERASE_END = 0x19000     # bank A rounded up to 4 KB sectors
CONFIG_START = 0x73000         # config, MAC, calibration, Bluetooth bonds: never written
MAC_SECTOR = 0x76000
SECTOR = 0x1000

STOCK_SHA256 = "dfd443c77f831008aa453ee2c1c9cb6871c36f8947c548e61d4387fba0a9da70"      # bank A of v1.09
STOCK_DAT_SHA256 = "87349e603bb92d6ae9ff6defb6f32b10de2f2d3252fe4e442fa7993f982f2a5a"  # 8BitDo's .dat file

UPDATE_RECORD = 0x3F000        # 52-byte record; byte +0x0c is the firmware version times 100 (0x6d = 1.09)
SUPPORTED_VERSION = 1.09
