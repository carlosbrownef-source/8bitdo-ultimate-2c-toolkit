# Hardware validation (2026-10-30)

Run on one Ultimate 2C Wireless controller, macOS 27 (Apple silicon), through the command line of this repository
(the same core the app uses); the web page and macOS app were checked separately against the simulation.

1. Back up by cable: the app read the whole flash twice and identified it as "unknown" (the controller carried an
   earlier development build).
2. Restore to 8BitDo's v1.09 (downloaded and hash-checked): dry run, write, read-back; a fresh backup identified as
   **stock v1.09**.
3. Patch Bluetooth Xbox + Bluetooth rumble + cable Xbox 360 (793 bytes of bank A): written and read back.
   - Cable: `045e:028e`, taken by Apple's Xbox driver.
   - Bluetooth (after forgetting and re-pairing): `045e:0b13`, the exact 283-byte Xbox descriptor, GameController
     category Xbox, every control read at full range, rumble felt, controller alive (about 115 reports/s).
4. Add dimmer LEDs as a separate write (45 bytes): written and read back; the LEDs are slightly dimmer (subtle by design:
   weak drive strength).
5. The final backup identified as stock v1.09 plus all four tweaks. The bug report contains no MAC or pairing bytes.

Not validated: other Ultimate 2C units, the dongle (refused by design), Linux.
