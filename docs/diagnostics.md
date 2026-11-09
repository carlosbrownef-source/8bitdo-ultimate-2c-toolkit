# Diagnostics

The Diagnostics tab helps you check how macOS sees the controller after installing tweaks, and gather information if something goes wrong.

- **Controller test:** shows what macOS's GameController reports, which is what a game gets, including the battery when macOS provides it. Press each button, stick and trigger to see it light up, and make the controller vibrate either the way a native game would or by sending the report straight to the controller. If only the direct report vibrates, the firmware isn't the problem.
- **Firmware details:** what the app read from the controller or the dongle, including where the version came from, whether a firmware update is pending, and how the bootloader identifies itself.
- **Problem report:** a text you can attach to a bug report.
- **Install Firmware 1.09 Anyway…:** the last resort for a controller whose firmware can't be identified.

The controller test is only available in the Mac app for now, because it uses macOS's GameController directly. Everything else in the tab also works when you run the app from source.
