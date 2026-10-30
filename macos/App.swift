// SPDX-License-Identifier: GPL-3.0-or-later
// A window around the local web UI: starts the bundled Python core, loads the address it prints, stops it on quit.
import AppKit
import IOKit.hid
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var core: Process?
    var buffer = Data()

    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        // The controller's update channel is an input-monitoring device: ask once, up front.
        if IOHIDCheckAccess(kIOHIDRequestTypeListenEvent) != kIOHIDAccessTypeGranted {
            _ = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)
        }
        web = WKWebView(frame: .zero)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "u2c-customfw"
        window.contentView = web
        window.center()
        window.makeKeyAndOrderFront(nil)
        installMenu()
        startCore()
    }

    func installMenu() {
        let main = NSMenu(), item = NSMenuItem(), menu = NSMenu()
        menu.addItem(withTitle: "Quit u2c-customfw", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = menu
        main.addItem(item)
        NSApp.mainMenu = main
    }

    func fail(_ message: String) {
        let escaped = message.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
        web.loadHTMLString("<body style='font:15px -apple-system;background:#15171a;color:#e6e8eb;padding:24px'><h3>Could not start</h3><pre>\(escaped)</pre></body>", baseURL: nil)
    }

    func startCore() {
        guard let res = Bundle.main.resourceURL else { return fail("no resources") }
        let p = Process()
        p.executableURL = res.appendingPathComponent("python/bin/python3")
        p.arguments = ["-m", "u2c_customfw.web"]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = res.appendingPathComponent("app").path
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p.environment = env
        let out = Pipe(), err = Pipe()
        p.standardOutput = out
        p.standardError = err
        out.fileHandleForReading.readabilityHandler = { [weak self] h in
            guard let self = self else { return }
            self.buffer.append(h.availableData)
            guard let text = String(data: self.buffer, encoding: .utf8) else { return }
            for line in text.split(separator: "\n") where line.hasPrefix("U2C_URL ") {
                h.readabilityHandler = nil
                if let url = URL(string: String(line.dropFirst("U2C_URL ".count))) {
                    DispatchQueue.main.async { self.web.load(URLRequest(url: url)) }
                }
            }
        }
        var errTail = Data()
        err.fileHandleForReading.readabilityHandler = { h in
            errTail.append(h.availableData)
            if errTail.count > 8192 { errTail = errTail.suffix(8192) }
        }
        p.terminationHandler = { [weak self] proc in
            if proc.terminationStatus != 0, let self = self {
                let msg = String(data: errTail, encoding: .utf8) ?? ""
                DispatchQueue.main.async { self.fail("The Python core stopped (status \(proc.terminationStatus)).\n\n\(msg)") }
            }
        }
        do { try p.run(); core = p } catch { fail("\(error)") }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    // Never end the app silently while a job (a write above all) is running: ask first.
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        web.evaluateJavaScript("typeof busy !== 'undefined' && busy === true") { result, _ in
            if (result as? Bool) == true {
                let alert = NSAlert()
                alert.messageText = "An operation is running"
                alert.informativeText = "Quitting now can leave the controller half-written. If that happens, put it in boot mode and use Diagnose and restore. Quit anyway?"
                alert.addButton(withTitle: "Keep running")
                alert.addButton(withTitle: "Quit anyway")
                NSApp.reply(toApplicationShouldTerminate: alert.runModal() == .alertSecondButtonReturn)
            } else {
                NSApp.reply(toApplicationShouldTerminate: true)
            }
        }
        return .terminateLater
    }
    func applicationWillTerminate(_ note: Notification) { core?.terminate() }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
