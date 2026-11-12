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

# Hardware validation of 0.4.0 (2026-11-07)

Run on the same controller, macOS 27.2 (Apple silicon), through the command line and small read-only tools, with live changes
sent by cable as the app sends them. Each item is the plan as written before the run, followed by what happened.

1. Done on 2026-11-07: with a threshold-0 build, noise at rest spans about 25 of 4,096 counts per axis, and 99 % of steps between samples stay within 11. Replaying the samples, 14 lets the noise through about once every 2 s, and 8 about 13 times a second, so `STICK_THRESHOLD` is 14.
   Installed on 2026-11-07 (7 bytes over the defaults): moving the left stick slowly by cable, the median step went from 637 to 467 of 32767 and 90 % of steps from 982 to 621, about 14/20. Released, it went back to 0 and sent nothing for 30 s. Over Bluetooth, a minute moving the sticks gave 111 reports per second, no disconnection, longest gap 60 ms.
2. Install 0.4 with defaults: every control behaves as on 0.3. Read `0x7a000` back.
   Done on 2026-11-07: restored the original 1.09 over the stack test build (4,042 bytes, no other block), then installed the app's default tweaks with the ring at 5 % (4,080 bytes). A backup identifies it, and against the 0.3 backup only the firmware area and `0x7a000` differ. `0x7a000` still held the record saved with the test build, since Restore leaves it, so the app's Reset to defaults put it back; the diagnostics tests then responded normally by cable and over Bluetooth.
3. Each setting by cable: dead zone, reach, curve and inversion on both sticks in the live view; trigger range; vibration at 0 and 50 % in a game by cable and over Bluetooth, with battery alerts unchanged; idle limit; buzz on connecting; L4 and R4 with a single button, several buttons and a trigger; the dead zone switch from the app and with Start + Select; button remapping with A and B swapped, and one button set to nothing.
   Partial, 2026-11-07, by cable with live changes, pairing the firmware's raw telemetry with what GameController reports: a
   30 % dead zone keeps the stick at 0 up to about a third of its travel (about 12 % at the default); reach 70 % gets to full at about
   60 % of the physical travel (about 84 % at the default); the soft curve gives less than linear at mid travel and the fast one more;
   inverting one axis flipped exactly that axis. LT starting at 30 % stays at 0 up to 29 % of its raw travel and then rises evenly;
   RT ending at 60 % is full at about 60 %. A and B swapped, X set to nothing, R4 as A and L4 as LB + RB + LT all arrived as set.
   The dead zone switch works from the app and with Start + Select, seen in the raw report (switched on, a stick at rest sends
   nothing; off, its noise), but GameController doesn't show it by cable: Apple's driver hides about the central 12 % of the travel
   on its own.
   Game vibration: by cable, with Xbox 360 rumble reports sent straight to the gamepad, 0 % doesn't vibrate, 50 % is weaker and
   100 % strong. Over Bluetooth, with Xbox's rumble report and the level saved (Fixes restarts the controller when it's unplugged,
   which drops live changes), 0 % doesn't vibrate and 50 % is weaker. The battery alerts call the motors directly, past this
   setting. GameController's haptics from a background command-line tool didn't vibrate at all, at any level.
   Saved with the buzz on connecting off and a 5-minute idle limit: turned on without the cable, it connected over Bluetooth without
   vibrating, and left alone it turned itself off 5 minutes 0 seconds after connecting.
4. Save, turn off and on, over cable and Bluetooth. Reset to defaults. Restore and install again: settings still apply.
   Done on 2026-11-07: saving, then turning off and on, kept the vibration level over Bluetooth (above). Reset to defaults saved
   the defaults, read back. With a 30 % left dead zone saved, Restore (4,080 bytes, no other block) and installing again kept the
   record, and the left stick again stayed at 0 for about a third of its travel while the right one, at the default, didn't.
5. Calibration with the guide, and sticks and triggers afterwards.
   Done on 2026-11-07, once: the guide's steps worked as written. Only the calibration sectors changed (`0x74000`, 14 bytes,
   and `0x75000`, 6 bytes). Afterwards, in the raw cable report with the dead zone off, both sticks reach -32768 and 32767 on each
   axis, rest within about 540 of 32767 of the centre (about as before), and both triggers reach 255.
6. Fixes: only sticks past a short test limit; the Mac's Bluetooth off after a minute idle; unplugging; a sleeping Mac with the cable in, which must not restart; a plain charger; the Bluetooth update no longer answering.
   2026-11-07, with a 5-minute idle limit saved: moving only the sticks over Bluetooth for 7 minutes kept it on, and left alone it
   turns off at 5 minutes exactly (item 3), so noise doesn't count. Unplugging restarts it and it's back on Bluetooth about 4 s later.
   After a minute idle, turning the Mac's Bluetooth off made it turn off within seconds, and it didn't come back when the Mac's
   Bluetooth did. That isn't the case the fix covers: stock's terminate callback (`0xa070`) powers off at once (`0xa0ac`, to
   `0xd8e8`) when the link ends with reason 19 (the host ended it, which turning Bluetooth off probably sends), and keeps
   searching on reason 8 (lost link), the case the counter reset is for. That case passed: after more than 30 minutes untouched,
   shut in a microwave oven (off), the link dropped, and taken out 19 s later it reconnected by itself. Stock would have turned
   off on the next tick. A plain charger (a power bank), plugged in
   and unplugged over Bluetooth, didn't restart it or drop the connection. Still to try: a sleeping Mac with the cable in (this
   Claude Code session holds a sleep assertion, so it needs the session closed), and the Bluetooth update.
7. Connection request: reports per second over 60 s, then 30 minutes with rumble. Soft start: low strengths from rest, both motors.
   Left out of 0.4 (Carlos, 2026-11-07): both tweaks were removed from the app until they can be tried. The sleeping-Mac check is postponed, and the Bluetooth update stays closed without a check on the controller.
8. 30 minutes of a game over Bluetooth with rumble on code running from the tail.
   Done on 2026-11-07 (at rest, with Xbox's rumble report sent every 20 s, 89 in all, and a 60-minute idle limit saved): 30 minutes, 199,718 reports at 111 per second, no disconnection, median gap 14.2 ms, 99 % within 30 ms, longest 76 ms.
9. Before publishing, the main stack's margin with a build compiled with `-DSTACK_TEST` (`firmware-src/settings.c`): how much stays unused after playing by cable and over Bluetooth, with every setting changed, saving, and rumble running. At least 100 of its 784 bytes should stay unused.
   Done on 2026-11-07: 128 bytes stayed unused after starting with the cable, and again after saving from the app, L4 + R4, play by cable, about 90 minutes over Bluetooth with rumble and plugging in again; nothing entered the dead code at `0x1210`. The deepest point comes when starting or when USB connects. Fixes, left out of the test build, add about 24 bytes. Opening the Settings tab repaints the test build's stack, so the app has to stay closed while measuring.
10. With the same build, whether the CPU ever sleeps: main-loop passes per second over Bluetooth and by cable, against about 66 radio events per second at 15 ms. Also how long a full charge lasts idle and while playing, as a baseline. This only measures.
   Done on 2026-11-07 for the loop: it averaged 6,239 passes per second over 2.5 hours, mostly over Bluetooth, and 770 to 1,760 by cable, so the CPU never sleeps. How long a charge lasts wasn't measured.

# Hardware validation of 1.0.0 (2026-11-07 to 2026-11-08)

Run on the same controller, macOS 27.2 (Apple silicon), with test builds of Processor rest (a deliberate hang, a time meter, a
battery log in an unused flash area), the command line of this repository and small read-only tools.

1. **Watchdog.** A deliberate hang restarts the controller about 3 s later: by cable, USB went away and came back within 0.5 s;
   over Bluetooth on battery it restarted and reconnected by itself. Turned off with Home on battery, it stayed off with the
   watchdog armed. Charging while off from a power bank for about 10 minutes, it stayed off and charged normally. Then 35 minutes
   of play over Bluetooth, with two Start + Select saves and a charger plugged in and out, all in one session with no restart.
   With the processor held in a 30 s busy loop, holding Home for 10 s or more still cut the power, so a hang can always be ended by
   hand.
2. **Processor rest.** The first build broke the Bluetooth link a second after connecting, because the processor didn't wake for
   the system timer; the shipped build wakes for it. With it: 25 minutes of play, nothing odd by feel; both sticks in circles for
   68 s gave 104 reports per second, median gap 14.8 ms (the Mac's 15 ms interval), 99 % within 28.1 ms, longest 45.6 ms. Rumble
   over Bluetooth at 30, 60 and 100 % and short pulses felt right, twice. A test build measured the share of time spent resting:
   60 % with the controller still and 62-63 % while playing.
3. **Battery.** A test build with Processor rest logged the battery once a minute in flash. On a Linux PC over Bluetooth: 296
   minutes on battery, 293 connected, no rumble, from 4136 mV and 100 % to 3970 mV and 77 % (the firmware's own percentage).
   There was no run without Processor rest to compare, so the app says it may make the battery last longer, not that it does.
4. **Faster button reading.** By cable, about 10 fast taps each, soft and firm, on the d-pad, LB, RB, A, B, X and Y: 104
   presses, none starting again within 20 ms of a release and none held under 15 ms.
5. **Connection request.** macOS sets 15 ms with peripheral latency 22 at connect and refuses any request from a gamepad, both
   the original 7.5 ms and one inside Apple's rules (seen in bluetoothd's log); the report rate didn't move. With the original
   request, Linux ran the link at about 12.2 ms by the firmware's own reading. The 12.5 ms request that every install now
   includes was installed on 2026-11-08 and hasn't been run on Linux or Windows yet.
6. **Installing over firmware the app doesn't recognise.** On 2026-11-08, over the battery log build (firmware 1.09 by its update
   record, not one of the app's builds): the check passed, the install wrote and read back, and the controller then read as the
   original 1.09 with all twelve tweaks of the final build and the Home ring at 5 %.
7. **Dongle, read only.** With the dongle alone, the app reads its firmware in about 7 s and identifies it by hash: v1.03 with
   the Xbox 360 change on the tester's dongle. By cable the controller presents as "8BitDo Ultimate 2C Wireless Controller" with
   bcdDevice `0x0114`, the same name and version as the dongle's X-input descriptor, so a paired dongle can't be told from the
   controller by its USB identity alone.

8. **Dongle over 2.4 GHz.** On 2026-11-08 the dongle's Xbox 360 change, with bcdDevice `0x0103`, was written by a separate
   tool and read back. With the controller on 2.4 GHz it presents as `045e:028e` version `0x0103`, and the controller test saw
   every control and rumble worked. With both sticks in circles for 63 s, 62,995 reports arrived: 1,000 per second, median gap
   1.0 ms, 99 % within 1.2 ms, longest 11.3 ms (over Bluetooth: 104 per second, median 14.8 ms). The app reads the paired
   dongle's firmware through it in about 4.5 s and shows it as the dongle with the controller connected. The app's own Back Up of the dongle ran on it the same day (about 45 s), and the app then read the dongle as 1.03 with the tweak, with its backup offered for Restore.

9. **Intel build.** Built for x86_64 with its own Python and run under Rosetta on the same Mac (both processes "X86-64 (translated)"): the window and pages load, the dongle is found and read through IOKit, identified by hash, and its backup recognised. Not yet run on an Intel Mac.

Still to do: Restore when a 4 KB block outside the firmware area differs from the backup; quitting or closing the window during
a real write; the 12.5 ms request on Linux or Windows; and, from 0.4, a sleeping Mac with the cable in and the closed Bluetooth
update.

# Hardware validation of 1.0.2 (2026-11-11)

Run with the 1.0.2 beta (1.0.2b1, the published build), on the same controller, macOS 27.2 (Apple silicon), through the macOS
app. Between steps, the controller was put in update mode and restarted from it with a script, not with L1 + R1 (see below).

1. **Reads by cable.** The app identified 1.09 with its eleven tweaks, the Settings tab loaded, and no newer version was offered.
   Asked for real, GitHub's latest release is offered to 1.0.0 with the right link and not to the beta.
2. **Update mode.** The app read and identified the firmware through the bootloader and backed up the whole flash in about
   1.5 minutes, so the bootloader's replies pass the new check on the address they echo.
3. **Restore and install again.** Restore to the original 1.09 (4,333 bytes, about 33 s), then the same tweaks (4,333 bytes,
   about 33 s). Each write kept `caffeinate -i -w <the core>` running, gone when it finished; the backup didn't start it. After
   Restore, the Settings tab showed no ring level and the install offered "Home ring: normal". A backup afterwards differs from
   the one before only in the two bytes of the installed ring level (5 % before, normal after); the pairings, the address and
   the settings record are unchanged. With 5 % saved from the Settings tab, the controller starts at 5 %.
4. **L4 and R4.** L4 mapped to A and saved stayed mapped after the Settings tab reloaded and after a restart, and pressing L4
   showed A in the controller test. It was then cleared and saved again.
5. **Update mode without buttons.** `81 05 00 51 00` on the update channel by cable restarts the controller into update mode
   within a second, with the original firmware or with tweaks, as it does on the dongle: its handler sets analog register
   `0x3c` to `0x5a`, which the bootloader checks at start-up. The bootloader's restart command (7) clears it and restarts
   into the firmware, as the controller again within about a second. Four times in a row, with no flash written. The app
   doesn't use it yet.

6. **Dongle, with the 1.0.2 build itself.** Alone, it read as 1.03 with the Xbox 360 change, and its backup matched the one from
   2026-11-08 byte for byte. Create Problem Report worked with it, alone and paired. Restore to the original 1.03 and installing
   the change again (8 bytes each, about 31 s, through its bootloader, with `caffeinate` during each write) left a backup identical
   to the one before. With the controller on 2.4 GHz it presents as `045e:028e` version `0x0103`: the app reads it through the
   dongle and keeps its writes for when the controller is off, the Settings tab says the dongle has no settings, the controller
   test finds the controller, and the check that the device by cable isn't the dongle refuses it.

The 1.0.2 build also read the controller by cable and in update mode before it was published.

Not validated: the crash message, which was tried with a simulated core.

# Hardware validation of 1.0.3 (2026-11-11)

Run on the same controller, macOS 27.2 (Apple silicon), with the 1.0.3 build through the macOS app, and the command line of the
same branch. Writes were made by cable; between them the controller was left as the app left it.

1. **Entering and leaving update mode.** The app's own code (`_into_update_mode`, the bootloader's restart command and the wait
   for the controller by cable) ran five times in a row with nothing written: update mode in 0.9 s, the bootloader identified
   as the controller's, back by cable in 1.0 to 1.2 s. Unplugging the cable doesn't leave update mode entered this way, since
   the battery keeps the flag; holding Home for about 12 seconds with the cable out does; the restart command also starts the
   firmware after entering with LB + RB.
2. **Check First by cable** reads through the update channel and leaves the controller running: installing what's there
   (6 s), installing other tweaks (6 s), restoring the original (7 s) and restoring the backup (22 s, which also compares the
   memory outside the firmware). Restore → Your Backup is offered by cable. Reading the firmware by cable now takes about
   4.8 s instead of 3.5 s, to find that backup. The app's core kept the same number of IOKit clients from task to task.
3. **Restore the original 1.09** (4,333 bytes): update mode, the write with `caffeinate` held throughout, and the restart. The
   controller came back as `2dc8:310a`, an identity this Mac blocked as a new accessory ("device functionality blocked by
   transport restrictions") until it was allowed, so the app didn't see it within 10 s and said so; its message now starts with
   allowing the accessory.
4. **Restore your backup** by cable, over the original: checked by cable, then again in update mode, written, and back as
   `045e:028e` with "The controller restarted with its new firmware", in about 1.5 minutes.
5. **Install by cable** without Finer stick movement (7 bytes, 41 s), then **install from update mode entered with LB + RB**
   with it again (7 bytes): both restarted the controller into its new firmware.
6. **Afterwards**, a backup by cable matched the one taken before these writes except the settings record's ring byte
   (`+25`), which holds the level installed and the level saved: normal installed, 5 % saved, as the controller had it.
