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

# Hardware validation of 0.2.0 (2026-11-05)

Run on the same controller, macOS 27.2 (Apple silicon), through the macOS app and the command line. Each install was
read back and identified afterwards.

- **Update mode:** the bootloader's identity query answers `0x301b`, shown under Firmware details. No update was pending.
- **Backups:** a backup taken before the controller was paired again still counts as the same unit. Installing with
  "your backup" finds the original firmware when the newest backup has tweaks.
- **Home ring:** 25 %, 5 %, 1 % and Off were installed and looked at, and 5 % was installed from the app. The ring blinks
  at its usual brightness while searching, then settles at the chosen level. It doesn't change while vibrating. 0.1 % was
  not looked at; it runs the same code as the other percentages.
- **Bluetooth:** all 19 controls, triggers and sticks respond. Vibrate like a game, Left, Right and Direct report are felt.
  macOS strips the report ID, so the direct report reaches the firmware as intended. The battery is shown through macOS.
  Home lights up in the test and doesn't open Apple Games, after macOS asks for permission the first time, and it opens
  Apple Games again after leaving the tab or quitting the app.
- **Cable:** all controls respond, vibration through macOS works, and Direct report is disabled. Switching to another app
  pauses the test, and it continues on returning.
- **Sticks:** recorded at the time as staying inside the circle at the diagonals, over Bluetooth and by cable. Start + Select
  switches a 14 % dead zone on and off; it doesn't limit the sticks to a circle. What was seen was the sticks' range with the
  unit's setting as it stood, which wasn't recorded.
- **Name:** macOS shows "8BitDo Ultimate 2C (X/S)" without pairing again.
- **Detection:** turning the controller off, connecting it and entering update mode are noticed without pressing Refresh.

Not validated: other Ultimate 2C units, rumble in CrossOver games, the dongle (refused by design), Linux.
