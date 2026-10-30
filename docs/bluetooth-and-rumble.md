# Bluetooth Xbox identity and rumble

## Why this makes macOS treat it as an Xbox controller

`AppleGameControllerPersonality.kext` matches Bluetooth Xbox pads on vendor `045e` and a product ID (`0b13`, `0b23`, `0b4f` for the Series pads), taken from the Device Information PnP ID, then GameController presents them as Xbox controllers. The patch sets the PnP ID to `045e:0b13` (version `0x0509`) and replaces the HID report map with the real Series X|S one (captured by xpadneo), so the data matches byte for byte.

## Changes

- PnP ID, report map pointer and length, output report ID 3, GAP appearance (gamepad `0x03c4`) and the name "8BitDo Ultimate 2C (One)" (the name fits in place, scan response included).
- New input packer: the 16-byte Xbox report 1 (4 sticks as u16, two 10-bit triggers, hat 1-8, 15 buttons, Share) built from the controller's state. The controller's L4/R4 and digital L2/R2 are not reported (a real Xbox pad has no such buttons).
- The output report gets a write callback (stock has none and rejects the write).

macOS caches a paired device's description: forget the controller and pair it again after flashing.

## Rumble

Stock firmware calls the motor setter `fa68(0, 0, 0)` on every main-loop pass in Bluetooth mode. That setter ignores a zero-hold call only while a hold is running, so a handler that sets a strength with no hold is overwritten before the 10 ms motor routine applies it. The handler therefore passes the Xbox duration (10 ms units) as the hold, and scales Xbox magnitudes (0-100) to the setter's 0-255. A 30-second continuous run at full strength on both motors did not hang the controller in testing.
