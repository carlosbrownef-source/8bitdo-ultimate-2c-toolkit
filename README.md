# u2c-customfw

Back up, patch and repair the firmware of the **8BitDo Ultimate 2C Wireless controller (firmware 1.09)**, so macOS treats it as an Xbox controller and every game sees it.

> ## READ THIS FIRST
> **This is a vibe-coded project.** It was written with an AI assistant and tested on a single controller.
>
> **It comes with NO WARRANTY of any kind, explicit or implied**, including any warranty of merchantability or fitness
> for a particular purpose. You use it entirely at your own risk.
>
> **By using this app you lose your controller's warranty.** Writing a modified firmware to the controller voids it.
>
> **It only works with the 8BitDo Ultimate 2C Wireless controller running firmware 1.09.** It does not work with the
> 2.4 GHz dongle, with other 8BitDo models, or with other firmware versions, and it refuses them.
>
> **It will probably break compatibility with 8BitDo's own apps**, both the Firmware Updater and Ultimate Software.
>
> **You can always return to stock.** The controller's bootloader is never modified, and Diagnose and restore puts back
> either your own backup or 8BitDo's firmware 1.09.

## What the tweaks do

| Tweak | Effect |
| --- | --- |
| Bluetooth: Xbox Series X/S controller | Over Bluetooth the controller presents as an Xbox Series X/S pad (`045e:0b13`), so macOS's GameController framework handles it natively (name "8BitDo Ultimate 2C (One)"). Needs a re-pair afterwards. |
| Bluetooth: rumble | Rumble works over Bluetooth (stock firmware switches the motors off in that mode). Needs the Xbox option. |
| Cable: wired Xbox 360 controller | Plugged in by cable it presents as a wired Xbox 360 pad (`045e:028e`), which Apple's own driver takes. |
| Dimmer LEDs | The three LEDs use weak drive strength: a little dimmer. |

Each tweak is a hash-checked set of byte edits to the stock v1.09 image; nothing else in the firmware changes, and the controller's bootloader, MAC, calibration and pairings are never written.

## Install (macOS, Apple silicon)

1. Download `u2c-customfw-<version>-macos-arm64.zip` from the releases page and unzip it.
2. Open the app once. macOS will block it because it is not signed: open **System Settings → Privacy & Security**, scroll to the message about u2c-customfw and click **Open Anyway** (right-click → Open no longer works on current macOS).
3. When asked, allow **Input Monitoring** (System Settings → Privacy & Security → Input Monitoring). The app needs it to talk to the controller.

Or from source, with Python 3.12+: `python3 -m u2c_customfw.web` prints a local address to open in a browser; `python3 -m u2c_customfw --help` is the command line.

## Use

1. **Back up** (controller plugged in by cable). Required before the first write; keep the file.
2. **Patch**: choose tweaks, put the controller in boot mode (power it fully off, hold L1+R1 while plugging in the cable; the LED blinks white), do a *dry run*, then *Write*. Afterwards unplug the cable; if a Bluetooth tweak changed, forget the controller in Bluetooth settings and pair it again (macOS caches the old description).
3. **Diagnose and restore**: if anything looks wrong, put the controller in boot mode and restore your backup, or 8BitDo's v1.09 (downloaded from 8BitDo's update server and checked against its known SHA-256).

Safeguards, enforced in the code: nothing is written below `0x6000` (bootloader) or at/above `0x73000` (configuration, MAC, calibration, Bluetooth pairings); a write needs a backup of the same unit (bootloader and MAC match); the firmware must be v1.09 stock or one of ours; the dongle is refused; restoring 8BitDo's v1.09 is refused unless the controller really is on 1.09 (read from its update record, or, if that is blank, identified by the hash of bank A or bank B) and is also refused when the version cannot be determined; every edit checks the stock bytes it replaces.

## Porting to Linux

The only OS-specific part is `u2c_customfw/transport/`. See [docs/porting.md](docs/porting.md).

## Documentation

- [docs/firmware-notes.md](docs/firmware-notes.md): flash layout, update and bootloader protocols, RAM code.
- [docs/bluetooth-and-rumble.md](docs/bluetooth-and-rumble.md): how the Bluetooth Xbox identity and rumble work.
- [firmware-src/README.md](firmware-src/README.md): the C and assembly we add, and how to rebuild it.

## License and credits

GPL-3.0-or-later; see `LICENSE` and [CREDITS.md](CREDITS.md). 8BitDo firmware is not included in this repository.
