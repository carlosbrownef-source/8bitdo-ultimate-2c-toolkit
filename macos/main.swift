// SPDX-License-Identifier: GPL-3.0-or-later
// A window around the local web UI: starts the bundled Python core, loads the address it prints, stops it on quit.
import AppKit
import IOKit.hid
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSToolbarDelegate, WKNavigationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var web: WKWebView!
    let diagnostics = Diagnostics()
    var core: Process?
    var buffer = Data()
    var coreURL: URL?   // the address the core printed, with its token

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
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1144, height: 718),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        // The title bar replaces the page's own top bar (hidden with ?native=1): name, what it is for, and Help.
        window.title = "U2C Firmware Toolkit"
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        window.subtitle = "v\(version) · 8BitDo Ultimate 2C Wireless · firmware 1.09 only"
        window.titlebarAppearsTransparent = true    // takes the window colour, so it blends into the page
        let toolbar = NSToolbar(identifier: "main")
        toolbar.delegate = self
        window.toolbar = toolbar
        window.toolbarStyle = .unified
        window.backgroundColor = background
        window.contentMinSize = NSSize(width: 760, height: 720)
        window.contentView = web
        window.delegate = self
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
        menu.addItem(withTitle: "Quit U2C Firmware Toolkit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = menu
        main.addItem(item)
        let editItem = NSMenuItem(), edit = NSMenu(title: "Edit")  // so ⌘C and ⌘A work in the page (the problem report)
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)
        NSApp.mainMenu = main
    }

    func fail(_ message: String, title: String = "Could not start", advice: String = "") {
        let html = { (s: String) in s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;") }
        web.loadHTMLString("<body style='font:15px -apple-system;background:#101215;color:#e8eaed;padding:24px'><h3>\(html(title))</h3>"
                           + (advice.isEmpty ? "" : "<p style='max-width:640px'>\(html(advice))</p>") + "<pre style='white-space:pre-wrap'>\(html(message))</pre></body>", baseURL: nil)
    }

    func startCore() {
        guard let res = Bundle.main.resourceURL else { return fail("no resources") }
        let p = Process()
        p.executableURL = res.appendingPathComponent("python/bin/python3")
        p.arguments = ["-m", "u2c_customfw.web"]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = env["U2C_CORE_PATH"] ?? res.appendingPathComponent("app").path   // macos/preview.sh runs the repository's core
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p.environment = env
        let out = Pipe(), err = Pipe()
        p.standardOutput = out
        p.standardError = err
        out.fileHandleForReading.readabilityHandler = { [weak self] h in
            let data = h.availableData
            guard let self = self, !data.isEmpty else { h.readabilityHandler = nil; return }  // empty: the core has gone
            self.buffer.append(data)
            guard let text = String(data: self.buffer, encoding: .utf8) else { return }
            for line in text.split(separator: "\n") where line.hasPrefix("U2C_URL ") {
                h.readabilityHandler = nil
                if let url = URL(string: String(line.dropFirst("U2C_URL ".count)) + "&native=1") {
                    DispatchQueue.main.async { self.coreURL = url; self.web.load(URLRequest(url: url)) }
                }
            }
        }
        var errTail = Data()
        let errLock = NSLock()   // written on the pipe's queue, read on the termination handler's
        err.fileHandleForReading.readabilityHandler = { h in
            let data = h.availableData
            guard !data.isEmpty else { h.readabilityHandler = nil; return }
            errLock.lock()
            errTail.append(data)
            if errTail.count > 8192 { errTail = errTail.suffix(8192) }
            errLock.unlock()
        }
        p.terminationHandler = { [weak self] proc in
            if proc.terminationStatus != 0, let self = self {
                err.fileHandleForReading.readabilityHandler = nil
                errLock.lock()
                errTail.append(err.fileHandleForReading.readDataToEndOfFile())   // the traceback may still be in the pipe
                let msg = String(decoding: errTail.suffix(8192), as: UTF8.self)    // a character cut at the start can't empty it
                errLock.unlock()
                let how = proc.terminationReason == .uncaughtSignal ? "signal" : "status"
                DispatchQueue.main.async {
                    let started = self.coreURL != nil   // it stopped while the app was in use, perhaps in the middle of a write
                    self.fail("The Python core stopped (\(how) \(proc.terminationStatus)).\n\n\(msg)",
                              title: started ? "The app stopped working" : "Could not start",
                              advice: started ? "If the controller or the dongle was being written, the write was interrupted. Quit, open the app again and use Restore. Put the controller in update mode first; the app puts the dongle in update mode by itself. Please report this, with the text below." : "")
                }
            }
        }
        do { try p.run(); core = p } catch { fail("\(error)") }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    /// Whether the core is writing to the controller. It asks the core, which knows even when the page doesn't (a lost
    /// event stream, a crashed web view). If the core can't be asked but is still running, it counts as writing.
    func writing() -> Bool {
        guard let page = coreURL, var parts = URLComponents(url: page, resolvingAgainstBaseURL: false),
              let token = parts.queryItems?.first(where: { $0.name == "token" })?.value else { return core?.isRunning ?? false }
        parts.path = "/api/busy"
        parts.queryItems = nil
        guard let url = parts.url else { return core?.isRunning ?? false }
        var request = URLRequest(url: url, timeoutInterval: 2)
        request.setValue(token, forHTTPHeaderField: "X-Token")
        var answer: Bool?
        let done = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: request) { data, _, _ in
            if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                answer = json["writing"] as? Bool
            }
            done.signal()
        }.resume()
        done.wait()
        return answer ?? (core?.isRunning ?? false)
    }

    // Never end the app silently while the controller is being written: ask first.
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard writing() else { return .terminateNow }
        let alert = NSAlert()
        alert.messageText = "Quit while the controller is being written?"
        alert.informativeText = "Quitting now can leave the controller half-written. Do not disconnect the controller or quit the app until the task finishes. If it's interrupted, put the controller in update mode and use Restore."
        alert.addButton(withTitle: "Don’t Quit")
        alert.addButton(withTitle: "Quit Anyway")
        return alert.runModal() == .alertSecondButtonReturn ? .terminateNow : .terminateCancel
    }

    // Closing the only window quits, so it asks the same way, and the window stays if the write goes on.
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        NSApp.terminate(nil)
        return false
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
