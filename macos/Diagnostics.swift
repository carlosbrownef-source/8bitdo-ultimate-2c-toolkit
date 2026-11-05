// SPDX-License-Identifier: GPL-3.0-or-later
// The bridge behind the page's controller test: what macOS's GameController reports, and three ways to make the
// controller vibrate. It only runs while the Diagnostics tab is open, and it never writes to the controller's memory.
import AppKit
import CoreHaptics
import GameController
import IOKit.hid
import WebKit

final class Diagnostics: NSObject, WKScriptMessageHandler {
    weak var web: WKWebView?
    private var timer: Timer?
    private var observers: [NSObjectProtocol] = []
    private var lastInput = ""
    private var home: GCControllerButtonInput?
    private var homeWas = GCControllerElement.SystemGestureState.enabled
    private var engines: [CHHapticEngine] = []

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let op = body["op"] as? String else { return }
        switch op {
        case "start": start()
        case "stop": stop()
        case "vibrate": vibrate(body["locality"] as? String ?? "default")
        case "direct": direct()
        default: break
        }
    }

    private var pad: GCController? { GCController.current ?? GCController.controllers().first }

    private func start() {
        stop()
        let center = NotificationCenter.default
        for name in [Notification.Name.GCControllerDidBecomeCurrent, .GCControllerDidConnect, .GCControllerDidDisconnect,
                     NSApplication.didBecomeActiveNotification, NSApplication.didResignActiveNotification] {
            observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in self?.sendState() })
        }
        sendState()
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in self?.sendInput() }
    }

    /// Also runs when the app quits, so the Home button never stays captured.
    func stop() {
        timer?.invalidate()
        timer = nil
        observers.forEach(NotificationCenter.default.removeObserver)
        observers = []
        releaseHome()
        lastInput = ""
    }

    private func captureHome(_ button: GCControllerButtonInput?) {
        guard button !== home else { return }
        releaseHome()
        guard let button = button else { return }
        homeWas = button.preferredSystemGestureState
        button.preferredSystemGestureState = .disabled
        home = button
    }

    private func releaseHome() {
        home?.preferredSystemGestureState = homeWas
        home = nil
    }

    private func sendState() {
        guard let pad = pad else {
            releaseHome()
            return send(["type": "state", "connected": false])
        }
        captureHome(pad.extendedGamepad?.buttonHome)
        send(["type": "state", "connected": true, "name": pad.vendorName ?? "Unknown controller", "category": pad.productCategory,
              "extended": pad.extendedGamepad != nil, "localities": localities(pad), "foreground": NSApp.isActive])
    }

    private func localities(_ pad: GCController) -> [String] {
        guard let available = pad.haptics?.supportedLocalities else { return [] }
        return [("default", GCHapticsLocality.default), ("left", .leftHandle), ("right", .rightHandle)]
            .filter { available.contains($0.1) }.map { $0.0 }
    }

    private func sendInput() {
        guard NSApp.isActive, let e = pad?.extendedGamepad else { return }
        let buttons: [(String, GCControllerButtonInput?)] = [
            ("A", e.buttonA), ("B", e.buttonB), ("X", e.buttonX), ("Y", e.buttonY), ("LB", e.leftShoulder), ("RB", e.rightShoulder),
            ("L3", e.leftThumbstickButton), ("R3", e.rightThumbstickButton), ("View", e.buttonOptions), ("Menu", e.buttonMenu), ("Home", e.buttonHome),
            ("Up", e.dpad.up), ("Down", e.dpad.down), ("Left", e.dpad.left), ("Right", e.dpad.right)]
        let event: [String: Any] = ["type": "input", "pressed": buttons.filter { $0.1?.isPressed == true }.map { $0.0 },
                                    "lx": e.leftThumbstick.xAxis.value, "ly": e.leftThumbstick.yAxis.value,
                                    "rx": e.rightThumbstick.xAxis.value, "ry": e.rightThumbstick.yAxis.value,
                                    "lt": e.leftTrigger.value, "rt": e.rightTrigger.value]
        guard let text = json(event), text != lastInput else { return }
        lastInput = text
        deliver(text)
    }

    private func vibrate(_ locality: String) {
        let where_: GCHapticsLocality = locality == "left" ? .leftHandle : locality == "right" ? .rightHandle : .default
        guard let haptics = pad?.haptics else { return result("vibrate", "This controller doesn't offer vibration.") }
        guard let engine = haptics.createEngine(withLocality: where_) else { return result("vibrate", "The vibration couldn't be started.") }
        do {
            try engine.start()
            let strength = CHHapticEventParameter(parameterID: .hapticIntensity, value: 1)
            let event = CHHapticEvent(eventType: .hapticContinuous, parameters: [strength], relativeTime: 0, duration: 0.7)
            try engine.makePlayer(with: CHHapticPattern(events: [event], parameters: [])).start(atTime: CHHapticTimeImmediate)
            engines.append(engine)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
                engine.stop()
                self?.engines.removeAll { $0 === engine }
            }
            result("vibrate", nil)
        } catch {
            result("vibrate", error.localizedDescription)
        }
    }

    /// Xbox's rumble report straight to the controller, skipping GameController: both main motors, level 100, 0.7 s.
    private func direct() {
        let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        IOHIDManagerSetDeviceMatching(manager, [kIOHIDVendorIDKey: 0x045E, kIOHIDProductIDKey: 0x0B13] as CFDictionary)
        IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        defer { IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone)) }
        let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
        let bluetooth = devices.first { (IOHIDDeviceGetProperty($0, kIOHIDTransportKey as CFString) as? String)?.contains("Bluetooth") == true }
        guard let device = bluetooth else { return result("direct", "No controller was found over Bluetooth.") }
        let report: [UInt8] = [0x03, 0x03, 0, 0, 100, 100, 70, 0, 0]  // report ID, then mask, LT, RT, strong, weak, duration, delay, loop
        let status = IOHIDDeviceSetReport(device, kIOHIDReportTypeOutput, 3, report, report.count)
        result("direct", status == kIOReturnSuccess ? nil : "The report couldn't be sent (IOReturn \(String(UInt32(bitPattern: status), radix: 16))).")
    }

    private func result(_ op: String, _ error: String?) {
        var event: [String: Any] = ["type": "result", "op": op, "ok": error == nil]
        if let error = error { event["error"] = error }
        send(event)
    }

    private func send(_ event: [String: Any]) {
        if let text = json(event) { deliver(text) }
    }

    private func json(_ event: [String: Any]) -> String? {
        guard let data = try? JSONSerialization.data(withJSONObject: event) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func deliver(_ text: String) {
        web?.evaluateJavaScript("window.u2cDiagnostics && window.u2cDiagnostics(\(text))")
    }
}
