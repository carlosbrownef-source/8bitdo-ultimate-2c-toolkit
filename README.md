# U2C Firmware Toolkit

<p align="center">
  <a href="https://github.com/carlosbrownef-source/8bitdo-ultimate-2c-toolkit/releases/latest"><img src="https://img.shields.io/github/v/release/carlosbrownef-source/8bitdo-ultimate-2c-toolkit" alt="Latest release"></a>
  <a href="https://github.com/carlosbrownef-source/8bitdo-ultimate-2c-toolkit/releases"><img src="https://img.shields.io/github/downloads/carlosbrownef-source/8bitdo-ultimate-2c-toolkit/total" alt="Downloads"></a>
  <img src="https://img.shields.io/badge/platform-macOS%2013%2B-blue" alt="macOS 13 or later">
  <img src="https://img.shields.io/github/license/carlosbrownef-source/8bitdo-ultimate-2c-toolkit" alt="GPL-3.0 license">
</p>

<p align="center">
  <img src="docs/images/firmware.png" alt="The Firmware tab, showing firmware 1.09 with its tweaks next to the backup and restore steps" width="420">
  <img src="docs/images/diagnostics.png" alt="The Diagnostics tab, testing a controller over Bluetooth" width="420">
</p>

U2C Firmware Toolkit is a toolkit for the **8BitDo Ultimate 2C Wireless** and its **2.4 GHz dongle** on a Mac: everything they need, in one app. It makes macOS and its games treat the controller as a native one, by cable, over Bluetooth and through the dongle, adds rumble and control over its light, and lets you test it, back both up and restore them. There are no drivers or background programs, because the changes live in the controller and the dongle themselves.

Out of the box, macOS and most Mac games see the Ultimate 2C as a generic HID device, not as a game controller. After this, they see an Xbox controller.

> **This is a vibe-coded project, written with an AI assistant (Opus 5.5). There's no warranty, and you use it at your own risk.** Installing modified firmware probably voids the controller's and the dongle's warranty. Please read the [full disclaimer](DISCLAIMER.md) and the [safeguards](SAFEGUARDS.md) before using it. Not affiliated with or endorsed by 8BitDo.

## What it does

- **Works as a native controller.** Over Bluetooth it presents itself as an Xbox Series X|S controller, by cable and through the 2.4 GHz dongle as an Xbox 360 controller, so macOS and its games recognise it every way.
- **Rumble over Bluetooth**, which the original firmware doesn't have.
- **Adjustable light.** Dim the ring around the Home button or turn it off, from the app or with L4 + R4.
- **Battery alerts** with the ring and the motors when the battery is low, and when charging starts and completes.
- **Settings that change at once**: dead zones, stick and trigger ranges, vibration strength, L4 and R4, button remapping and the power-off time.
- **Fewer interruptions and a resting processor**: playing only with the sticks no longer turns it off, and over Bluetooth the processor rests between radio events.
- **Tests, backs up and restores** the controller and the dongle, and goes back to 8BitDo's original firmware at any time.

It works with the **Ultimate 2C Wireless on firmware 1.09** and its **2.4 GHz dongle on firmware 1.03**, on Macs with Apple silicon or Intel and macOS 13 or later. It doesn't work with other models. [docs/tweaks.md](docs/tweaks.md) explains each change in detail.

## Install (macOS 13 or later)

1. Download the zip for your Mac from the [releases page](https://github.com/carlosbrownef-source/8bitdo-ultimate-2c-toolkit/releases/latest) and unzip it: `firmware-toolkit-<version>-macos-arm64.zip` for Apple silicon, or `firmware-toolkit-<version>-macos-x86_64.zip` for Intel. The Intel build has been tested under Rosetta, not yet on an Intel Mac.
2. Open the app once. macOS will block it because it is not signed: open **System Settings → Privacy & Security**, scroll to the message about the app and click **Open Anyway** (right-click → Open no longer works on current macOS). You can also remove it from quarantine with `xattr`, as the [FAQ](docs/faq.md#macos-wont-open-the-app) shows.
3. When asked, allow **Input Monitoring** (System Settings → Privacy & Security → Input Monitoring). The app needs it to talk to the controller and the dongle.

Or with [Homebrew](https://github.com/carlosbrownef-source/homebrew-tap), which replaces step 1:

```sh
# the app
brew trust --cask carlosbrownef-source/tap/firmware-toolkit
brew install --cask carlosbrownef-source/tap/firmware-toolkit
# the command line only
brew install carlosbrownef-source/tap/firmware-toolkit
```

Or from source, with Python 3.12+: `python3 -m u2c_customfw.web` prints a local address to open in a browser; `python3 -m u2c_customfw --help` is the command line. The command-line tool and the Python package keep the project's first name, `u2c-customfw`.

## Use

The app's **Help** button explains each step and why each tweak is needed.

1. **Back up** with the controller connected by cable. The backup holds your controller's calibration and Bluetooth pairing keys too, and the app requires one before it writes anything.
2. **Install tweaks.** Choose them, put the controller in update mode (turn it fully off, then hold LB + RB while plugging in the cable; the small light below the Home ring will blink white), use *Check First*, then *Install Tweaks…*. If a Bluetooth tweak changed, remove the controller from Bluetooth settings and pair it again.
3. **Restore** your backup, or 8BitDo's original firmware 1.09, from update mode, whenever you want to go back.

For the **dongle**, turn the controller off and plug the dongle in on its own. The steps are the same: back it up, switch its one tweak on or off and install, or restore. The app puts it in update mode by itself.

If something doesn't work, the [FAQ](docs/faq.md) covers the usual problems.

## Documentation

- [SAFEGUARDS.md](SAFEGUARDS.md): every check the app makes before and while it writes.
- [docs/faq.md](docs/faq.md): installing, update mode, re-pairing, rumble and compatibility.
- [docs/tweaks.md](docs/tweaks.md): what each tweak changes, for the controller and the dongle.
- [docs/settings.md](docs/settings.md): the Settings tab, which changes the controller without reinstalling.
- [docs/diagnostics.md](docs/diagnostics.md): the controller test, firmware details and problem reports.
- [docs/firmware-notes.md](docs/firmware-notes.md): flash layout, update and bootloader protocols, RAM code.
- [docs/bluetooth-and-rumble.md](docs/bluetooth-and-rumble.md): how the Bluetooth Xbox identity and rumble work.
- [docs/porting.md](docs/porting.md): porting the app to Linux.
- [firmware-src/README.md](firmware-src/README.md): the C and assembly the tweaks add, and how to rebuild it.
- [docs/releasing.md](docs/releasing.md): publishing a new version, and how the Homebrew tap follows it.

## Other projects

Other people reached the same goal on their own, and these are worth a look:

- **[vomba/8bitdo-ultimate-2c-apple](https://github.com/vomba/8bitdo-ultimate-2c-apple)** changes just six bytes of firmware 1.09 so Apple uses its SN30 Pro+ profile: the smallest possible patch, without rumble. Its owner reports that it also works on Apple TV.
- **[Crazyawk/8bitdo-ultimate2c-macos-rumble](https://github.com/Crazyawk/8bitdo-ultimate2c-macos-rumble)** brings Bluetooth rumble to CrossOver games, with patched firmware and an SDL shim.
- **[lodo4nik/8bitdo-sdl-macos-fix](https://github.com/lodo4nik/8bitdo-sdl-macos-fix)** helps SDL games and CrossOver recognise the controller on macOS without touching its firmware, by changing one setting each time you log in.
- **[amirreza225/8bitdo-ultimate-2c-mac](https://github.com/amirreza225/8bitdo-ultimate-2c-mac)** makes the Ultimate 2C **Wired** work in Chrome and Amazon Luna, with a browser extension. This app doesn't support that model.

## Credits

This project builds on the reverse engineering of [jgus-org/8bitdo-2c-re-flake](https://github.com/jgus-org/8bitdo-2c-re-flake), the Xbox Series X|S descriptor captured by [xpadneo](https://github.com/atar-axis/xpadneo), the Home ring method of [supercypok/ultimate2c-ring](https://github.com/supercypok/ultimate2c-ring), and notes from [Crazyawk](https://github.com/Crazyawk/8bitdo-ultimate2c-macos-rumble), [vomba](https://github.com/vomba/8bitdo-ultimate-2c-apple) and [MoridaDE](https://github.com/MoridaDE/8bitdo-2c-battery-tray). No code was copied. [CREDITS.md](CREDITS.md) says what came from each.

## License

GPL-3.0-or-later; see `LICENSE`. 8BitDo firmware is not included in this repository. Not affiliated with or endorsed by 8BitDo.
