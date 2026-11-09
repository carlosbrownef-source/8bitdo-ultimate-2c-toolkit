# What the tweaks do

| Tweak | Effect |
| --- | --- |
| Xbox Series X\|S controller over Bluetooth | Over Bluetooth the controller presents as an Xbox Series X\|S pad (`045e:0b13`), so macOS's GameController framework handles it natively (name "8BitDo Ultimate 2C (X/S)"). Needs a re-pair afterwards (or macOS may still detect it as a HID device). |
| Rumble over Bluetooth | Rumble works over Bluetooth (the original firmware switches the motors off in that mode). Needs the Xbox tweak as it uses its profile. In rare cases it could make the controller stop responding. This hasn't been observed. |
| Xbox 360 controller over cable | Plugged in by cable it presents as a wired Xbox 360 pad (`045e:028e`), which Apple's own driver takes. It changes the least code of all the tweaks. |
| Dimmer LEDs | Slightly lowers the brightness of the controller's three lights, by giving them weak drive strength. It is subtle: to really change the ring around the Home button, use Home Ring in the Settings tab. |
| Battery alerts | The ring blinks slowly while charging and quickly at 15 % or less, even if you turned it off. The motors give one short pulse when charging starts, one long pulse when it completes, and two short pulses at 5 % or less, again every 5 minutes. Needs the Home ring's code. |
| Controller settings | Adds what the Settings tab changes. Needs the Home ring's code. |
| Fixes | Moving a stick counts as using the controller, which the original firmware only notices through buttons, so playing only with sticks no longer turns it off after 15 minutes. A dropped connection gets its full search time. Unplugging the cable in the Bluetooth position restarts the controller, so it finds the Mac at once. It also closes the firmware update over Bluetooth, which needs no encryption. Needs the Home ring's code. |
| Processor rest | Over Bluetooth on battery, the original firmware keeps the processor busy in a loop. This stops it for up to 1 ms at a time between radio events, woken by the radio, the system timer or its own 1 ms timer. This may make the battery last longer. A watchdog restarts the controller if the main loop ever stops for 3 s. On by default. Needs the Home ring's code. |
| Finer stick movement | The firmware ignores stick changes of up to 20 of about 4,000 steps, which makes slow movement advance in small jumps. This lowers that threshold to 14, just above the noise measured on one controller, and reads the sticks twice per report. A stick held still away from the centre may still move by one step now and then. Off by default. Needs the Home ring's code. |
| Faster button reading | The firmware reads the buttons and triggers every 5 ms. This reads them every 2.5 ms, so a press arrives about 1.25 ms sooner on average. The time Home must be held and turbo's rate are rescaled to stay the same. About 100 fast taps on one controller showed no double presses, but the firmware has no other debounce, so a worn button could bounce. Off by default. |
| Bluetooth connection request | Included in every install, with no switch: the controller asks for a 12.5 ms connection interval with no peripheral latency, instead of 7.5 ms with latency 59. macOS refuses any such request from a gamepad and keeps 15 ms; Linux and Windows may follow it. |
| Home ring | The code that drives the ring around the Home button, installed with any tweak that needs it. Its level is set in the Settings tab or with L4 + R4: normal, 25 %, 5 %, 1 %, 0.1 % or off (the percentage is PWM duty, not perceived brightness). It still blinks while searching or pairing, at its usual brightness, and settles at your level once connected. Installing keeps the ring's level as it is. |

Each tweak is a hash-checked set of byte edits to the original firmware 1.09; nothing else in the firmware changes, and the controller's bootloader, MAC, calibration and pairings are never written. See [SAFEGUARDS.md](../SAFEGUARDS.md) for every check the app makes.

## The dongle's tweak

| Tweak | Effect |
|---|---|
| Xbox 360 controller over 2.4 GHz | With the controller connected through it, the dongle presents as a wired Xbox 360 pad (`045e:028e`, class `ff`), which Apple's own driver takes. Its bcdDevice becomes `0x0103` instead of `0x0114`, so the app can tell a paired dongle from the controller by cable without reading it; Apple's driver matches on vendor, product and interface class only. 9 bytes of its X-input device descriptor. |

The app puts the dongle in update mode by itself whenever it writes; [SAFEGUARDS.md](../SAFEGUARDS.md) describes how it checks and writes the dongle. With the controller connected through the dongle, the app reads the dongle but changes nothing. The controller's own firmware can only be read by cable.
