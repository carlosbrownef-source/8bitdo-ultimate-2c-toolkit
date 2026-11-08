// SPDX-License-Identifier: GPL-3.0-or-later
// Only for tests: loaded when the address has ?diagsim=<state>. Simulates what the page can't get in a browser:
// the Mac app's bridge, and a controller that isn't in update mode. &scenario= plays a short script.
(() => {
  const query = new URLSearchParams(location.search), mode = query.get("diagsim"), scenario = query.get("scenario");
  const realFetch = window.fetch;
  const json = (data) => new Response(JSON.stringify(data), { status: 200 });
  window.fetch = async (url, options) => {
    const path = String(url);
    document.getElementById("diag-fetch").textContent += path + " ";
    const device = window.simReplugged ? "bluetooth_xbox" : { bt: "bluetooth_xbox", btstock: "bluetooth", cable: "cable", web: "cable", none: "bluetooth_xbox", background: "bluetooth_xbox", noext: "bluetooth_xbox", busy: "bluetooth_xbox", dongle: "dongle" }[mode];
    if (path.startsWith("/api/restore")) document.getElementById("diag-posted").textContent += options.body + " ";
    if (query.get("job") && /^\/api\/(backup|patch|restore)/.test(path)) return new Response('{"started": "job"}', { status: 202 });
    if (query.get("job") && path.startsWith("/api/events")) return new Response(JOB_EVENTS[query.get("job")].map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""), { status: 200 });
    if (path.startsWith("/api/settings") && options && options.method === "POST") {
      document.getElementById("diag-posted").textContent += options.body + " ";
      if (query.get("slow")) await new Promise((r) => setTimeout(r, 2000));
      if (query.get("settingsfail") || (window.simFailSave && options.body.includes('"save"'))) return new Response(JSON.stringify({ error: "The controller said no." }), { status: 409 });
      return json({ ok: true, values: Object.fromEntries((await (await realFetch(url.split("?")[0] + "?" + location.search.slice(1), { headers: options.headers })).json()).fields.map((f) => [f.name, f.default])) });
    }
    if (path.startsWith("/api/settings") && query.get("settings")) {
      const answer = await (await realFetch(url, options)).json();
      return json({ ...answer, available: true, note: "", values: Object.fromEntries(answer.fields.map((f) => [f.name, f.default])), dead_zone_off: false, mapping: { r4: 0, l4: query.get("mapped") ? 1 << 14 : 0 } });
    }
    if (path.startsWith("/api/ring")) return query.get("ringfail") ? new Response(JSON.stringify({ error: "The controller said no." }), { status: 409 }) : json({ ok: true });
    if (path.startsWith("/api/firmware") && device === "bluetooth_xbox") return json({ note: "Connect the controller by cable to see or change its firmware. Over Bluetooth, you can test it in Diagnostics and change the Home ring in Settings." });
    if (path.startsWith("/api/firmware") && device === "dongle") return json({ error: "That is the 2.4 GHz dongle, which this app does not support." });
    if (path.startsWith("/api/firmware") && query.get("permission")) return json({ error: "macOS refused access to the controller. Allow Input Monitoring for this app in System Settings > Privacy & Security > Input Monitoring, then try again.", permission: true });
    const answer = await realFetch(url, options);
    if (path.startsWith("/api/firmware") && query.get("tweaks")) {  // &tweaks=all: the default tweaks with the ring at 5 %
      const got = await answer.json(), all = query.get("tweaks") === "all";
      if (!got.tweaks) return json(got);
      const recipes = all ? ["bt_xbox", "bt_rumble", "cable_360", "dim_leds", "battery_alerts", "settings", "fixes", "cpu_rest", "ring_5"] : ["bt_xbox", "ring_5", ...(query.get("settings") ? ["settings"] : [])];
      const tweaks = got.tweaks.map((t) => t.key === "ring" ? { ...t, title: "Home ring: 5 %", on: true } : { ...t, on: recipes.includes(t.key) });
      return json({ ...got, recipes, titles: all ? tweaks.filter((t) => t.on).map((t) => t.title) : ["Dimmer LEDs", "Home ring: 5 %"], tweaks, ring_level: 2, outdated: !!query.get("outdated") });
    }
    if (path.startsWith("/api/firmware") && query.get("identity") === "none") return json({ ...(await answer.json()), boot_identity: null });
    if (path.startsWith("/api/state") && (device || query.get("nobackup"))) {
      const got = await answer.json();
      return json({ ...got, ...(device ? { devices: [{ mode: device, name: "simulated" }] } : {}), ...(query.get("nobackup") ? { backups: [] } : {}) });
    }
    return answer;
  };

  const JOB_EVENTS = {  // &job=: what a task's event stream says, without running it
    backup: [{ type: "log", text: "Backup saved as “controller-20261108-012334.bin”. The controller has the original firmware 1.09." }, { type: "done", message: "Backup saved as “controller-20261108-012334.bin”. The controller has the original firmware 1.09.", unchanged: false }],
    check: [{ type: "done", message: "The check passed and nothing was written. Installing changes 4,452 bytes of the firmware, with Dimmer LEDs.", unchanged: false }],
    install: [{ type: "progress", label: "write", done: 50, total: 100 }, { type: "done", message: "Installed. Unplug the controller and connect it again.", unchanged: false }],
    unchanged: [{ type: "done", message: "The controller already has this firmware, so nothing was written.", unchanged: true }],
    refused: [{ type: "error", message: "This controller has firmware 1.08, and this app only supports 1.09, so nothing was written." }],
  };
  const PAD = { type: "state", connected: true, name: "8BitDo Ultimate 2C (X/S)", category: "Xbox One", extended: true, localities: ["default", "left", "right"], transport: "Bluetooth Low Energy", foreground: true };
  if (query.get("battery")) { const [level, state] = query.get("battery").split(","); PAD.battery = { level: +level, state }; }
  const STATES = { bt: PAD, btstock: PAD, busy: PAD, boot: PAD, cable: { ...PAD, name: "Xbox 360 Controller", category: "Xbox 360", transport: "USB" }, none: { type: "state", connected: false },
    background: { ...PAD, foreground: false }, noext: { ...PAD, extended: false } };
  const REST = { lx: 0, ly: 0, rx: 0, ry: 0, lt: 0, rt: 0, pressed: [] };
  const input = (e) => window.u2cDiagnostics({ type: "input", ...REST, ...e });
  const snap = () => { document.getElementById("diag-snap").textContent += document.getElementById("test-body").innerHTML.includes("disabled") ? " disabled " : ""; document.getElementById("diag-snap").textContent += document.getElementById("test-body").textContent; };
  const snapIdle = () => { document.getElementById("diag-snap").textContent += $("idle").hidden ? "" : $("idle").textContent; };
  const clickOp = (op) => document.querySelector(`[data-op="${op}"]`).click();
  const press = () => { input({ pressed: ["A"] }); input({ lx: 0.8, ly: 0.6 }); input({ lx: 0.8, ly: 0.6, lt: 0.5 }); };
  const UNANSWERED = ["vibrate", "vibrateleave", "vibratestate", "lateresult"];
  const SCRIPTS = {
    press,
    batterychange: () => { input({ pressed: ["A"] }); window.u2cDiagnostics({ ...PAD, battery: { level: 0.55, state: "discharging" } }); },
    leave: () => { press(); showTab("firmware"); showTab("diagnostics"); },
    disconnect: () => { press(); window.u2cDiagnostics({ type: "state", connected: false }); snap(); window.u2cDiagnostics({ ...PAD, name: "Another Pad" }); },
    late: () => { input({ pressed: ["A"] }); showTab("firmware"); input({ pressed: ["B"] }); },
    vibrate: () => { clickOp("default"); clickOp("default"); snap(); },
    vibrateleave: () => { clickOp("default"); showTab("firmware"); showTab("diagnostics"); setTimeout(() => { clickOp("default"); snap(); }, 100); },
    vibratestate: () => { clickOp("default"); window.u2cDiagnostics({ ...STATES[mode], name: "Another Pad", localities: ["default"] }); },
    lateresult: () => { clickOp("left"); setTimeout(() => { clickOp("default"); window.u2cDiagnostics({ type: "result", op: "vibrate", id: 1, ok: true }); snap(); }, 3300); },
    inputafterjob: () => { busy = true; render(); busy = false; input({ pressed: ["A"] }); render(); },
    vibrateok: () => clickOp("default"),
    vibrateerror: () => clickOp("default"),
    direct: () => clickOp("direct"),
    defaultonly: () => window.u2cDiagnostics({ ...PAD, localities: ["default"] }),
    report: () => document.getElementById("report-open").click(),
    replugged: () => { window.simReplugged = true; },
    installed: () => { document.getElementById("diag-snap").textContent = tweaks().join(); },
    keptchoice: () => { document.querySelector('[data-ring="ring_1"]').click(); refresh(); setTimeout(() => { document.getElementById("diag-snap").textContent = tweaks().join(); }, 1000); },
    noalerts: () => { document.querySelector('.tweak[value="battery_alerts"]').click(); document.querySelector('.tweak[value="settings"]').click(); document.querySelector('.tweak[value="fixes"]').click(); document.querySelector('.tweak[value="cpu_rest"]').click(); document.getElementById("diag-snap").textContent = tweaks().join(); },
    setvibration: () => document.querySelector('[data-field="vibration"] [data-value="50"]').click(),
    setandsave: () => { document.querySelector('[data-field="vibration"] [data-value="50"]').click(); setTimeout(() => $("settings-save").click(), 200); },
    setandfailsave: () => { window.simFailSave = true; document.querySelector('[data-field="vibration"] [data-value="50"]').click(); setTimeout(() => $("settings-save").click(), 200); },
    dragdz: () => { const c = document.querySelector('[data-field="dz_l"]'); c.value = 5; c.dispatchEvent(new Event("input")); c.value = 9; c.dispatchEvent(new Event("input")); c.dispatchEvent(new Event("change")); },
    invert: () => { document.querySelector('[data-field="invert"][data-bit="0"]').click(); setTimeout(() => document.querySelector('[data-field="invert"][data-bit="2"]').click(), 200); },
    liveinput: () => window.u2cDiagnostics({ type: "input", ...REST, lx: 0.5, ly: -0.5, lt: 0.5 }),
    leavesettings: () => showTab("firmware"),
    settingstodiag: () => showTab("diagnostics"),
    mapa: () => { document.querySelector('[data-slot="r4"][data-bit="13"]').click(); setTimeout(() => document.querySelector('[data-slot="r4"][data-bit="12"]').click(), 200); },
    dzoff: () => document.getElementById("dead-zone-off").click(),
    remap: () => { const c = document.querySelector('[data-field="remap_13"]'); c.value = 12; c.dispatchEvent(new Event("change")); },
    remapreset: () => { const c = document.querySelector('[data-field="remap_13"]'); c.value = 12; c.dispatchEvent(new Event("change")); setTimeout(() => { $("settings-reset").click(); setTimeout(() => { $("confirm-yes").click(); $("confirm").onclose(); }, 200); }, 200); },
    resetopen: () => $("settings-reset").click(),
    restoreask: () => $("restore-backup").click(),
    restorecheck: () => $("restore-backup-dry").click(),
    installask: () => $("patch-write").click(),
    backupjob: () => $("backup").click(),
    quit: () => $("disclaimer-quit").click(),
    gotofirmware: () => $("settings-goto").click(),
    privacy: () => $("privacy-open").click(),
    details: () => $("details").click(),
    helpopen: () => { $("help-open").click(); setTimeout(() => { document.getElementById("diag-snap").textContent = `${document.activeElement.id} ${$("help").scrollTop}`; }, 100); },
    notweaks: () => { tweakBoxes().forEach((x) => { x.checked = false; }); render(); },
    checkjob: () => runJob("Checking…", "/api/patch", { tweaks: ["dim_leds"], base: "backup", write: false }, "Check passed"),
    installjob: () => { $("patch-write").click(); setTimeout(() => { $("confirm-yes").click(); $("confirm").onclose(); setTimeout(snapIdle, 0); }, 200); },
    resetyes: () => { $("settings-reset").click(); setTimeout(() => { $("confirm-yes").click(); $("confirm").onclose(); }, 200); },  // headless Chrome holds back the close event
    ringlevel: () => document.querySelector('[data-live="1"]').click(),
    ringreread: () => { document.querySelector('[data-live="1"]').click(); setTimeout(refresh, 300); },
    ringsave: () => document.getElementById("ring-save").click(),
    reopen: () => { showTab("firmware"); showTab("diagnostics"); },
    latebt: () => { window.simReplugged = true; window.u2cDiagnostics({ type: "state", connected: false }); window.u2cDiagnostics(PAD); },
  };

  if (mode !== "web") {
    window.webkit = { messageHandlers: { diagnostics: { postMessage(m) {
      document.getElementById("diag-sent").textContent += JSON.stringify(m) + " ";
      if (m.op === "start") window.u2cDiagnostics(STATES[mode]);
      if (m.op === "ring") window.u2cDiagnostics(query.get("ringfail") ? { type: "result", op: "ring", id: m.id, ok: false, error: "The report failed" } : { type: "result", op: "ring", id: m.id, ok: true });
      if ((m.op === "vibrate" || m.op === "direct") && !UNANSWERED.includes(scenario))
        window.u2cDiagnostics(scenario === "vibrateerror" ? { type: "result", op: m.op, id: m.id, ok: false, error: "The engine failed" } : { type: "result", op: m.op, id: m.id, ok: true });
    } } } };
  }
  for (const id of ["diag-sent", "diag-snap", "diag-fetch", "diag-posted"]) { const p = document.createElement("pre"); p.id = id; p.hidden = true; document.body.append(p); }
  addEventListener("DOMContentLoaded", () => {
    if (mode === "busy") setTimeout(() => { busy = true; render(); }, 300);
    if (SCRIPTS[scenario]) setTimeout(SCRIPTS[scenario], 1000);
  });
})();
