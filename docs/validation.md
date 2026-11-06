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

# Hardware validation of 0.3.0 (2026-11-06)

Run on the same controller, macOS 27.2 (Apple silicon), through the macOS app and the command line.

- **Install over 0.2.0:** the command line wrote 1250 bytes in update mode. A backup read by cable afterwards identifies the
  five tweaks plus Battery alerts, and no longer as outdated. Compared with the backup before it, only the firmware area and
  the saved ring level (settings field +25) differ. The pairings and the controller's address are unchanged.
- **Battery alerts, at 100 %:** plugging in gives one short pulse and a slow blink for a few seconds, then the ring settles.
- **Home ring, by cable and over Bluetooth:** the level changes at once from the app. A saved level is back after turning the
  controller off and on. L4 + R4 steps through the levels by cable and over Bluetooth.
- **Saving during use:** over Bluetooth, with L4 + R4 pressed more than 6 times in 3 minutes (each press saves after 3 s),
  reports arrived at 116 per second with no disconnection. The median gap was 14.6 ms and the longest 59 ms.
- **Bluetooth test tab:** controls, triggers, sticks and the vibration tests respond. The battery is shown through macOS.
- **A native game (SDL, Xbox mode):** a Pokémon port plays without drops, and vibrates when it should.
- **A game through Steam and NotProton:** the controls work. The game doesn't vibrate, so rumble there wasn't tried.
- **Restore and install again:** the app restored the original 1.09 over 0.3. A backup identifies it as original, the payload
  matches 8BitDo's hash, the area past the payload is blank, and nothing outside the firmware area changed. Installing the same
  tweaks from the app gave a flash identical to the first install, and the saved ring level came back.

Not validated: the alerts with a really drained battery (near 15 % and 5 %) and the pulse when charging completes. The pulses and
blink patterns were tried on the controller with a test build that simulates those states.

# Pending for 0.4.0

Nothing here has run on a controller yet. Each write needs its own go-ahead.

1. Measure stick noise with `tools/sticknoise` in the private notes to choose `STICK_THRESHOLD`.
2. Install 0.4 with defaults: every control behaves as on 0.3. Read `0x7a000` back.
3. Each setting by cable: dead zone, reach, curve and inversion on both sticks in the live view; trigger range; vibration at 0 and 50 % in a game by cable and over Bluetooth, with battery alerts unchanged; idle limit; buzz on connecting; L4 and R4 with a single button, several buttons and a trigger; the dead zone switch from the app and with Start + Select; button remapping with A and B swapped, and one button set to nothing.
4. Save, turn off and on, over cable and Bluetooth. Reset to defaults. Restore and install again: settings still apply.
5. Calibration with the guide, and sticks and triggers afterwards.
6. Fixes: only sticks past a short test limit; the Mac's Bluetooth off after a minute idle; unplugging; a sleeping Mac with the cable in, which must not restart; a plain charger; the Bluetooth update no longer answering.
7. Connection request: reports per second over 60 s, then 30 minutes with rumble. Soft start: low strengths from rest, both motors.
8. 30 minutes of a game over Bluetooth with rumble on code running from the tail. A painted-stack build for the main stack's margin.
