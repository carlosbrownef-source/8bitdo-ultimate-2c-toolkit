// SPDX-License-Identifier: GPL-3.0-or-later
// A window around the local web UI: starts the bundled Python core, loads the address it prints, stops it on quit.
import AppKit
import IOKit.hid
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSToolbarDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    let diagnostics = Diagnostics()
    var core: Process?
    var buffer = Data()

    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        // The controller's update channel is an input-monitoring device: ask once, up front.
        if IOHIDCheckAccess(kIOHIDRequestTypeListenEvent) != kIOHIDAccessTypeGranted {
            _ = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)
        }
        let background = NSColor(srgbRed: 0x10 / 255.0, green: 0x12 / 255.0, blue: 0x15 / 255.0, alpha: 1)  // the page's --bg
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(diagnostics, name: "diagnostics")
        web = WKWebView(frame: .zero, configuration: configuration)
        diagnostics.web = web
        web.navigationDelegate = self
        web.underPageBackgroundColor = background
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 920, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        // The title bar replaces the page's own top bar (hidden with ?native=1): name, what it is for, and Help.
        window.title = "u2c-customfw"
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        window.subtitle = "v\(version) · 8BitDo Ultimate 2C Wireless · firmware 1.09 only"
        window.titlebarAppearsTransparent = true    // takes the window colour, so it blends into the page
        let toolbar = NSToolbar(identifier: "main")
        toolbar.delegate = self
        window.toolbar = toolbar
        window.toolbarStyle = .unified
        window.backgroundColor = background
        window.contentMinSize = NSSize(width: 760, height: 640)
        window.contentView = web
        window.center()
        window.makeKeyAndOrderFront(nil)
        installMenu()
        startCore()
    }

    static let helpItem = NSToolbarItem.Identifier("help")
    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { [.flexibleSpace, Self.helpItem] }
    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { [.flexibleSpace, Self.helpItem] }
    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier id: NSToolbarItem.Identifier, willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        let item = NSToolbarItem(itemIdentifier: id)
        item.label = "Help"
        item.image = NSImage(systemSymbolName: "questionmark.circle", accessibilityDescription: "Help")
        item.isBordered = true
        item.target = self
        item.action = #selector(showHelp)
        return item
    }
    // If the page goes away without saying so, the test must not keep the Home button captured.
    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) { diagnostics.stop() }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { diagnostics.stop() }

    @objc func showHelp() { web.evaluateJavaScript("document.getElementById('help-open').click()") }

    func installMenu() {
        let main = NSMenu(), item = NSMenuItem(), menu = NSMenu()
        menu.addItem(withTitle: "Quit u2c-customfw", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = menu
        main.addItem(item)
        let editItem = NSMenuItem(), edit = NSMenu(title: "Edit")  // so ⌘C and ⌘A work in the page (the problem report)
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)
        NSApp.mainMenu = main
    }

    func fail(_ message: String) {
        let escaped = message.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
        web.loadHTMLString("<body style='font:15px -apple-system;background:#101215;color:#e8eaed;padding:24px'><h3>Could not start</h3><pre>\(escaped)</pre></body>", baseURL: nil)
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
                if let url = URL(string: String(line.dropFirst("U2C_URL ".count)) + "&native=1") {
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
                alert.informativeText = "Quitting now can leave the controller half-written. If that happens, put it in update mode and use Restore. Quit anyway?"
                alert.addButton(withTitle: "Keep running")
                alert.addButton(withTitle: "Quit anyway")
                NSApp.reply(toApplicationShouldTerminate: alert.runModal() == .alertSecondButtonReturn)
            } else {
                NSApp.reply(toApplicationShouldTerminate: true)
            }
        }
        return .terminateLater
    }
    func applicationWillTerminate(_ note: Notification) {
        diagnostics.stop()
        core?.terminate()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
