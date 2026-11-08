// SPDX-License-Identifier: GPL-3.0-or-later
const token = new URLSearchParams(location.search).get("token") || "";
if (new URLSearchParams(location.search).has("native")) document.body.classList.add("native");  // in the Mac app, whose title bar shows the name and Help
const $ = (id) => document.getElementById(id);
const setOn = (el, on) => { el.classList.toggle("on", on); el.setAttribute("aria-pressed", on); };  // a segmented choice or a chip
const api = async (method, path, body) => {
  const r = await fetch(path, { method, headers: { "X-Token": token }, body: body ? JSON.stringify(body) : undefined });
  const text = await r.text();
  let data = {}; try { data = JSON.parse(text); } catch (e) { data = { error: text }; }
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
};

const ICON = {
  ok: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8.5l3.2 3.2L13 4.5"/></svg>',
  no: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
  dash: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 8h8"/></svg>',
  warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/></svg>',
  plug: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3v5M15 3v5M6 8h12v4a6 6 0 0 1-12 0zM12 18v3"/></svg>',
};

/* Ultimate 2C, drawn from scratch: offset sticks, d-pad lower left, ABXY upper right, home button with its LED ring. */
const stick = (x, y, k) => `<circle cx="${x}" cy="${y}" r="19" fill="#1c2026"/><g data-k="${k}"><circle cx="${x}" cy="${y}" r="13.5" fill="#4b525c"/><circle cx="${x}" cy="${y}" r="9" fill="#424851"/></g>`;
const face = (x, y, t) => `<circle data-k="${t}" cx="${x}" cy="${y}" r="8.6" fill="#4b525c"/><text x="${x}" y="${y + 2.9}" text-anchor="middle" font-size="8.5" font-weight="600" fill="#b9c0c9" font-family="-apple-system,sans-serif">${t}</text>`;
const pad = (led, dim, gradient = "g") => `<svg viewBox="0 0 300 172" fill="none" role="img" aria-label="Controller"><defs><linearGradient id="${gradient}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a4049"/><stop offset="1" stop-color="#2a2f36"/></linearGradient></defs>
<path data-k="LB" d="M66 32c7-11 29-14 41-9" stroke="#454b54" stroke-width="9" stroke-linecap="round"/><path data-k="RB" d="M234 32c-7-11-29-14-41-9" stroke="#454b54" stroke-width="9" stroke-linecap="round"/>
<path d="M105 24L195 24C217.5 22 235.5 26 245.4 36C259.8 52 267 92 265.2 128C263.4 160 241.8 170 231 156C223.8 146 216.6 132 198.6 128L101.4 128C83.4 132 76.2 146 69 156C58.2 170 36.6 160 34.8 128C33 92 40.2 52 54.6 36C64.5 26 82.5 22 105 24Z" fill="url(#${gradient})" stroke="#4d545e" stroke-width="1.5" ${dim ? 'stroke-dasharray="5 4"' : ""}/>
${stick(81, 62, "LS")}${stick(182, 100, "RS")}
<circle cx="118" cy="100" r="20" fill="#30353d"/><path d="M112.5 85h11v9.5h9.5v11h-9.5v9.5h-11v-9.5h-9.5v-11h9.5z" fill="#4b525c"/>
<rect data-k="Up" x="112.5" y="85" width="11" height="9.5" fill="transparent"/><rect data-k="Down" x="112.5" y="105.5" width="11" height="9.5" fill="transparent"/><rect data-k="Left" x="103" y="94.5" width="9.5" height="11" fill="transparent"/><rect data-k="Right" x="123.5" y="94.5" width="9.5" height="11" fill="transparent"/>
${face(215, 43, "Y")}${face(198, 60, "X")}${face(232, 60, "B")}${face(215, 77, "A")}
<circle data-k="View" cx="120" cy="40" r="4.5" fill="#454b54"/><circle data-k="Menu" cx="180" cy="40" r="4.5" fill="#454b54"/><circle cx="135" cy="59" r="4.5" fill="#454b54"/><circle cx="165" cy="59" r="4.5" fill="#454b54"/><circle cx="150" cy="59" r="1.6" fill="#1c2026"/>
<circle data-k="Home" cx="150" cy="40" r="8" fill="#30353d" stroke="${led || "#4d545e"}" stroke-width="2.4"/>${led ? `<circle cx="150" cy="40" r="13" stroke="${led}" stroke-width="5" opacity=".18"/>` : ""}
</svg>`;

const CONTROLLER = ["cable", "cable_360", "boot"];
let st = null, fw = null, reading = false, busy = false, base = "backup";

const tweakBoxes = () => [...document.querySelectorAll(".tweak")];
const ringButtons = () => [...document.querySelectorAll("#ring button")];
const ringChoice = () => ringButtons().find((b) => b.classList.contains("on"));
const RING_CODE_USERS = ["battery_alerts", "settings", "fixes", "stick_precision", "cpu_rest"];
const needsRingCode = () => tweakBoxes().some((x) => RING_CODE_USERS.includes(x.value) && x.checked);
const tweaks = () => [...tweakBoxes().filter((x) => x.checked).map((x) => x.value), ...(ringChoice().dataset.ring ? [ringChoice().dataset.ring] : needsRingCode() ? ["ring_normal"] : [])];
const tweakTitles = () => [...tweakBoxes().filter((x) => x.checked).map((x) => x.parentElement.lastElementChild.firstChild.textContent),
  ...(ringChoice().dataset.ring || needsRingCode() ? [`Home ring: ${ringChoice().textContent.toLowerCase()}`] : [])];

function lastBackup(names) {  // controller-YYYYMMDD-HHMMSS….bin, oldest first
  const m = names.length && names[names.length - 1].match(/controller-(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)/);
  if (!m) return "";
  const d = new Date(+m[1], m[2] - 1, +m[3]), time = `${m[4]}:${m[5]}`;
  const day = d.toDateString() === new Date().toDateString() ? "today" : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  return `Last backup: ${day}, ${time}`;
}

function hero(devs, ctrl, boot) {
  const dongle = devs.find((d) => d.mode === "dongle"), bt = devs.find((d) => d.mode.startsWith("bluetooth")), err = devs.find((d) => d.mode === "error");
  let cls = "", title = "Firmware not read", note = "", chips = null;
  if (err) [cls, title, note] = ["bad", "Can't look for controllers", err.name];
  else if (!ctrl && !bt && !dongle) [cls, title, note] = ["none", "No controller found", "Connect it by cable, or put it in update mode."];
  else if (!ctrl && dongle) [cls, title, note] = ["none", "This is the 2.4 GHz dongle", "The app works only with the controller itself. Connect the controller by cable."];
  else if (reading) title = "Reading the firmware…";
  else if (fw && fw.error) [cls, title, note] = ["bad", "Can't read the firmware", fw.error];
  else if (fw && fw.note) [title, note] = [!ctrl && bt ? "Connected over Bluetooth" : title, fw.note];
  else if (fw && fw.known) {
    title = fw.recipes.length ? "Firmware 1.09 with tweaks" : "Original firmware 1.09";
    note = fw.version_from && fw.version_from !== "unknown" ? "Version read from the controller" : "";
    chips = fw.tweaks;
  } else if (fw && fw.version && fw.version.toFixed(2) !== "1.09")
    [cls, title, note] = ["bad", `Firmware ${fw.version.toFixed(2)} isn't supported`, "This app only works with firmware 1.09. Update the controller with 8BitDo's own updater first, or restore your backup."];
  else if (fw && fw.version) [cls, title, note] = ["", "Unrecognised firmware 1.09", "It doesn't match the original firmware 1.09 or this app's tweaks, perhaps a test build or firmware modified outside this app. Installing tweaks replaces it with the original 1.09 plus the tweaks you choose."];
  else if (fw) [cls, title, note] = ["bad", "Unknown firmware", "It doesn't match the original firmware 1.09, with or without this app's tweaks. It may be another firmware version, which you can update with 8BitDo's own updater, or firmware modified outside this app, which restoring your backup replaces."];

  const badge = ctrl ? `${boot ? "Update mode" : "Connected by cable"} · 8BitDo Ultimate 2C Wireless`
    : dongle ? "2.4 GHz dongle" : bt ? "Connected over Bluetooth · 8BitDo Ultimate 2C Wireless" : "Not connected";
  $("hero").className = "hero compact " + cls;
  $("badge").className = "badge " + (cls === "bad" ? "bad" : boot ? "isboot" : ctrl || bt ? "ok" : "");
  $("badge-text").textContent = badge;
  $("fw-title").textContent = title;
  $("fw-note").textContent = note;
  $("privacy-open").hidden = !(fw && fw.permission && bridge());
  const led = cls === "none" ? null : cls === "bad" ? "#e8695b" : boot ? "#ffffff" : getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  $("pic").innerHTML = pad(led, cls === "none");
  const n = chips ? chips.filter((t) => t.on).length : 0;
  $("sumrow").hidden = !chips;
  $("sum").textContent = !n ? "No tweaks installed." : `${n} ${n === 1 ? "tweak" : "tweaks"} installed.`;
  const box = $("chips"); box.textContent = ""; showDetails(detailsOpen && !!chips);
  const order = [...tweakBoxes().map((x) => x.value), "ring"];   // installed first, each group as the toggles, the Home ring last
  for (const t of (chips || []).slice().sort((a, b) => b.on - a.on || order.indexOf(a.key) - order.indexOf(b.key))) {
    const c = document.createElement("span"); c.className = "chip" + (t.on ? " on" : "");
    c.innerHTML = t.on ? ICON.ok : ICON.dash; c.append(t.title); box.append(c);
  }
}

let detailsOpen = false;
function showDetails(open) {
  $("chips").hidden = !open; $("details").textContent = open ? "Hide Details" : "Show Details"; $("details").setAttribute("aria-expanded", open);
}

function render() {
  const devs = st ? st.devices : [];
  const ctrl = devs.find((d) => CONTROLLER.includes(d.mode)), boot = !!ctrl && ctrl.mode === "boot";
  const backed = !!st && st.backups.length > 0, off = busy || reading, on109 = !!fw && !!fw.version && fw.version.toFixed(2) === "1.09";
  const patchable = boot && backed && tweaks().length > 0 && !(fw && fw.known === false && !on109);
  hero(devs, ctrl, boot);

  $("last-backup").textContent = st ? lastBackup(st.backups) : "";
  $("backup-connect").hidden = !!ctrl;
  const pre = (el, ok, yes, no) => { el.className = ok ? "ok" : ""; el.innerHTML = ok ? ICON.ok : ICON.no; el.append(ok ? yes : no); };
  pre($("pre-backup"), backed, "Backup saved", "No backup yet");
  pre($("pre-boot"), boot, "In update mode", "Not in update mode");
  $("boot-box").className = "boot" + (boot ? " ok" : "");
  $("boot-icon").innerHTML = boot ? ICON.ok.replace("<svg", '<svg width="20"') : ICON.plug;
  $("boot-title").textContent = boot ? "The controller is in update mode" : "Update mode";
  $("boot-text").textContent = boot ? "You can check or install now." : "Turn the controller fully off, then hold LB + RB while plugging in the cable. The light will blink white.";

  const xbox = tweakBoxes().find((x) => x.value === "bt_xbox"), rumble = tweakBoxes().find((x) => x.value === "bt_rumble");
  if (!xbox.checked) rumble.checked = false;
  tweakBoxes().forEach((x) => { x.disabled = busy || (x === rumble && !xbox.checked); x.parentElement.classList.toggle("off", x.disabled); });
  ringButtons().forEach((b) => (b.disabled = busy));
  const installWhy = !tweaks().length ? "Choose at least one tweak." : !fw || fw.known !== false || on109 ? ""
    : fw.version ? "This app only installs tweaks over firmware 1.09." : "This firmware can't be identified. Restore your backup first.";
  $("choose-one").textContent = installWhy; $("choose-one").hidden = !installWhy;

  const can = { backup: !!ctrl, "patch-dry": patchable, "patch-write": patchable,
    "restore-backup-dry": boot && !!fw && !!fw.restore_backup, "restore-backup": boot && !!fw && !!fw.restore_backup, "restore-stock-dry": boot && backed && on109, "restore-stock": boot && backed && on109,
    "force-open": boot && backed, "report-open": true, refresh: true };
  for (const [id, ok] of Object.entries(can)) $(id).disabled = off || !ok;
  $("backup").classList.toggle("sec", backed);   // once there's a backup, installing is the main step
  const stockWhy = !boot || !backed || !fw || fw.error || on109 ? "" : fw.version ? `Not available, because this controller has firmware ${fw.version.toFixed(2)}.`
    : "Not available, because the firmware version can't be identified.";
  $("restore-stock-why").textContent = stockWhy; $("restore-stock-why").hidden = !stockWhy;
  const restoreWhy = !boot ? "Put the controller in update mode to restore." : !backed ? "Back up the controller first to restore your backup." : "";
  $("restore-why").textContent = restoreWhy; $("restore-why").hidden = !restoreWhy;
  const backupWhy = boot && backed && !!fw && "restore_backup" in fw && !fw.restore_backup ? "Not available, because no backup of this controller has firmware this app recognises." : "";
  $("restore-backup-why").textContent = backupWhy; $("restore-backup-why").hidden = !backupWhy;
  const hot = !!fw && fw.known === false && !fw.version && !fw.error;
  $("force-zone").classList.toggle("hot", hot);
  $("force-hint").hidden = !hot;
  $("strip-alert").hidden = !(hot && tab === "firmware");
  details();
  settingsRender();
  diagnosticsRender();
}

const TABS = ["firmware", "settings", "diagnostics"];
let tab = "firmware";
function showTab(name) {
  if (name !== tab) {  // both tabs listen to the bridge, so the one being left stops first
    if (tab === "diagnostics") diagnosticsHide();
    if (tab === "settings") settingsHide();
    if (name === "diagnostics") diagnosticsShow();
    if (name === "settings") settingsShow();
  }
  tab = name;
  for (const t of TABS) {
    $(`tab-${t}`).hidden = name !== t;
    $(`strip-${t}`).classList.toggle("on", name === t); $(`strip-${t}`).setAttribute("aria-selected", name === t);
  }
  render();
}

const VERSION_FROM = { "update record": "The controller's update record", "bank A hash": "The installed firmware", "bank B hash": "The second copy of the firmware", unknown: "It couldn't be determined" };
const WHO = { 0x301b: "controller", 0x301c: "2.4 GHz dongle" };
const firmwareName = () => !fw.known ? "Unknown" : fw.recipes.length ? `1.09 with ${fw.recipes.length} ${fw.recipes.length === 1 ? "tweak" : "tweaks"}${fw.titles && fw.titles.length ? `: ${fw.titles.join(", ")}` : ""}` : "Original 1.09";
function details() {
  const box = $("details-body"), inUpdateMode = !!st && st.devices.some((d) => d.mode === "boot");
  const say = (text) => { box.innerHTML = ""; const p = document.createElement("p"); p.style.marginBottom = 0; p.textContent = text; box.append(p); };
  if (reading) return say("Reading the firmware…");
  if (!fw) return say("Connect the controller by cable, or put it in update mode, to read its firmware.");
  if (fw.error) return say(fw.error);
  if (fw.note) return say(fw.note);
  const id = fw.boot_identity;
  const rows = [["Firmware", firmwareName()], ["Version read from", VERSION_FROM[fw.version_from] || fw.version_from],
    ["Pending update", fw.pending ? "Yes. It could replace the tweaks the next time the controller starts." : "None"],
    ["Update-mode identity", !inUpdateMode ? "Only available in update mode" : id == null ? "No answer" : `0x${id.toString(16)} · ${WHO[id] || "unknown device"}`]];
  const dl = document.createElement("dl"); dl.className = "rows";
  for (const [k, v] of rows) { const t = document.createElement("dt"), d = document.createElement("dd"); t.textContent = k; d.textContent = v; dl.append(t, d); }
  box.innerHTML = ""; box.append(dl);
}

const STEPS = { "pass 1": [0, 50], "pass 2": [50, 50], write: [0, 100] };  // progress labels from the core
const setPct = (p) => { $("prog-bar").style.width = p + "%"; $("pc").textContent = p + " %"; $("prog").setAttribute("aria-valuenow", p); };
const LOST = "The app lost track of the task, which may still be running. Do not disconnect the controller until it has had time to finish, then read the firmware again.";
function line(text, bad) {
  const el = $("log"), s = document.createElement("span");
  if (bad) s.className = "e";
  s.textContent = text + "\n"; el.append(s); el.scrollTop = el.scrollHeight;
}

async function runJob(label, path, body, doneText) {  // doneText: the status when it worked, such as "Backup saved"
  busy = true; render();
  $("log").textContent = ""; $("log").hidden = true; $("log-toggle").hidden = false; $("log-toggle").textContent = "Show log ▴";
  $("dock").className = "dock run"; $("dock-status").textContent = label; $("dock-message").hidden = true;
  $("idle").textContent = "Do not disconnect the controller or quit the app until this finishes."; $("idle").hidden = !(body && body.write);
  $("prog").hidden = $("pc").hidden = false; setPct(0);
  let end = null, started = false;
  try {
    await api("POST", path, body);
    started = true;
    const r = await fetch("/api/events?token=" + encodeURIComponent(token));
    const reader = r.body.getReader(), dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      let i; while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        if (!chunk.startsWith("data: ")) continue;
        const e = JSON.parse(chunk.slice(6));
        if (e.type === "log") line(e.text);
        else if (e.type === "progress") { const [from, span] = STEPS[e.label] || [0, 100]; setPct(Math.floor(from + (span * e.done) / Math.max(e.total, 1))); }
        else if (e.type === "done") end = e;
        else if (e.type === "error") { end = e; line(e.message, true); }
      }
    }
  } catch (e) { line(e.message, true); end = { type: "error", message: started ? LOST : e.message }; }
  end = end || { type: "error", message: LOST };   // the stream ended without saying how the task did
  const ok = end.type === "done";
  $("dock").className = "dock " + (ok ? "done" : "err"); $("dock-status").textContent = !ok ? "Not completed" : end.unchanged ? "No changes needed" : doneText;
  $("dock-message").textContent = end.message || ""; $("dock-message").hidden = !end.message; $("idle").hidden = true;
  if (ok) setPct(100);
  busy = false; refresh();
}

function ask(title, text, chips, yes, kind = "safe") {  // kind: "install" (the warranty line and danger styling), "danger" or "safe"
  $("confirm-title").textContent = title; $("confirm-text").textContent = text; $("confirm-yes").textContent = yes;
  $("confirm-yes").className = kind === "safe" ? "" : "danger";
  $("confirm-icon").hidden = kind === "safe"; $("confirm-warranty").hidden = kind !== "install";
  const box = $("confirm-chips"); box.textContent = "";
  for (const c of chips) { const s = document.createElement("span"); s.textContent = c; box.append(s); }
  const d = $("confirm");
  return new Promise((resolve) => {
    let v = false;
    $("confirm-yes").onclick = () => { v = true; d.close(); };
    $("confirm-no").onclick = () => d.close();
    d.onclose = () => resolve(v);
    d.showModal();
  });
}

function renderDisclaimer(md) {  // "# title", paragraphs, **bold**: no HTML from the text is ever interpreted
  const box = $("disclaimer-text"); box.textContent = "";
  for (const para of md.split(/\n\s*\n/).map((x) => x.trim()).filter(Boolean)) {
    const el = document.createElement(para.startsWith("# ") ? "h3" : "p");
    para.replace(/^# /, "").replace(/\n/g, " ").split(/(\*\*[^*]+\*\*)/).forEach((part) => {
      if (part.startsWith("**")) { const b = document.createElement("strong"); b.textContent = part.slice(2, -2); el.append(b); }
      else if (part) el.append(document.createTextNode(part));
    });
    box.append(el);
  }
}

let refreshing = false, refreshAgain = false;  // one read of the controller at a time; a change during it reads again after
async function refresh() {
  if (refreshing) { refreshAgain = true; return; }
  refreshing = true;
  try {
    try { st = await api("GET", "/api/state"); }
    catch (e) { st = { devices: [{ mode: "error", name: "Can't reach the app: " + e.message }], backups: [] }; fw = null; return render(); }
    $("version").textContent = "v" + st.version;
    renderDisclaimer(st.disclaimer);
    if (!st.accepted && !$("disclaimer").open) $("disclaimer").showModal();
    fw = null; render(); await readFirmware();
  } finally {
    refreshing = false;
    if (refreshAgain) { refreshAgain = false; refresh(); }
  }
}

let matched = "";
function matchInstalled() {  // start from what's installed, so installing doesn't drop a tweak by surprise; the person's choices stay until other firmware is read
  const key = fw && fw.known && fw.recipes ? fw.recipes.join() : "";
  if (!key || key === matched) return;
  matched = key;
  tweakBoxes().forEach((x) => (x.checked = fw.recipes.includes(x.value)));
  const level = ringButtons().find((b) => fw.recipes.includes(b.dataset.ring)) || ringButtons()[0];
  ringButtons().forEach((b) => setOn(b, b === level));
}

let fwSeq = 0;
async function readFirmware() {  // read-only; skipped while a job runs, and the job buttons wait for it
  if (busy || !st.devices.some((d) => CONTROLLER.includes(d.mode) || d.mode === "dongle" || d.mode.startsWith("bluetooth"))) return;
  const mine = ++fwSeq; reading = true; render();
  let f;
  try { f = await api("GET", "/api/firmware"); } catch (e) { f = { error: e.message }; }
  if (mine !== fwSeq) return;
  fw = f; reading = false; matchInstalled(); render();
}

document.querySelectorAll("[data-icon]").forEach((e) => (e.innerHTML = ICON[e.dataset.icon]));
document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", b.classList.contains("on")));
$("disclaimer").oncancel = (e) => e.preventDefault();
$("disclaimer-quit").hidden = !bridge();   // declining: only the Mac app can quit itself
$("disclaimer-quit").onclick = () => bridge().postMessage({ op: "quit" });
$("accept").onclick = async () => { await api("POST", "/api/accept"); $("disclaimer").close(); refresh(); };
$("refresh").onclick = refresh;
$("details").onclick = () => { detailsOpen = !detailsOpen; showDetails(detailsOpen); };
TABS.forEach((t) => ($(`strip-${t}`).onclick = () => showTab(t)));
$("force-go").onclick = () => showTab("diagnostics");
$("privacy-open").onclick = () => bridge().postMessage({ op: "privacy" });
$("help-open").onclick = () => $("help").showModal();
$("help-close").onclick = () => $("help").close();
tweakBoxes().forEach((x) => (x.onchange = render));
ringButtons().forEach((b) => (b.onclick = () => { ringButtons().forEach((o) => setOn(o, o === b)); render(); }));
document.querySelectorAll("[data-base]").forEach((b) => (b.onclick = () => {
  base = b.dataset.base; document.querySelectorAll("[data-base]").forEach((x) => setOn(x, x === b));
}));
$("log-toggle").onclick = () => { const l = $("log"); l.hidden = !l.hidden; $("log-toggle").textContent = l.hidden ? "Show log ▴" : "Hide log ▾"; };

$("backup").onclick = () => runJob("Backing up…", "/api/backup", null, "Backup saved");
$("patch-dry").onclick = () => runJob("Checking…", "/api/patch", { tweaks: tweaks(), base, write: false }, "Check passed");
$("patch-write").onclick = async () => {
  if (await ask("Install these tweaks?", "This changes the controller's firmware. Installing modified firmware probably voids the controller\'s warranty.", tweakTitles(), "Install", "install"))
    runJob("Installing…", "/api/patch", { tweaks: tweaks(), base, write: true }, "Tweaks installed");
};
$("restore-backup-dry").onclick = () => runJob("Checking…", "/api/restore", { source: "backup", backup: fw.restore_backup.name, write: false }, "Check passed");
$("restore-stock-dry").onclick = () => runJob("Checking…", "/api/restore", { source: "stock", write: false }, "Check passed");
$("restore-backup").onclick = async () => {
  const b = fw.restore_backup;
  if (await ask("Restore your backup?", `This replaces the controller's firmware with your backup “${b.name}”, made on ${b.taken}, which has ${b.firmware}.`, [], "Restore"))
    runJob("Restoring…", "/api/restore", { source: "backup", backup: b.name, write: true }, "Backup restored");
};
$("restore-stock").onclick = async () => {
  if (await ask("Restore the original firmware 1.09?", "This replaces the controller's firmware with 8BitDo's original 1.09, downloaded from 8BitDo. Your settings, pairings and calibration stay as they are.", [], "Restore", "danger"))
    runJob("Restoring…", "/api/restore", { source: "stock", write: true }, "Original firmware restored");
};
$("force-open").onclick = () => {
  const d = $("force"), tick = $("force-understand"), yes = $("force-yes");
  tick.checked = false; yes.disabled = true;
  tick.onchange = () => { yes.disabled = !tick.checked; };
  $("force-no").onclick = () => d.close();
  yes.onclick = () => { d.close(); runJob("Installing…", "/api/restore", { source: "stock", write: true, force_unknown: true }, "Original firmware installed"); };
  d.showModal();
};
$("report-open").onclick = async () => {
  try { $("report-text").textContent = (await api("POST", "/api/report", { macos: diagnosticsSummary() || undefined, firmware: fw && fw.known !== undefined ? firmwareName() : undefined, boot_identity: fw && fw.boot_identity != null ? fw.boot_identity : undefined, pending: fw && fw.pending })).text; } catch (e) { $("report-text").textContent = e.message; }
  $("report").showModal();
};
$("report-copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("report-text").textContent); $("report-copy").textContent = "Copied"; }
  catch (e) { getSelection().selectAllChildren($("report-text")); }  // then ⌘C
};
$("report-close").onclick = () => { $("report").close(); $("report-copy").textContent = "Copy"; };
render(); refresh();

// Notice a controller being connected, disconnected or put in update mode, without pressing Refresh.
const deviceKey = (state) => state ? state.devices.map((d) => `${d.mode}:${d.vendor}:${d.product}:${d.name}`).sort().join() : "";  // a paired dongle has the controller's ID
const WATCH_MS = 2500;
setInterval(async () => {
  if (busy || reading || refreshing || document.hidden) return;
  let now;
  try { now = await api("GET", "/api/state"); } catch (e) { return; }
  if (!busy && !reading && !refreshing && deviceKey(now) !== deviceKey(st)) refresh();
}, WATCH_MS);
if (new URLSearchParams(location.search).has("diagsim")) showTab(new URLSearchParams(location.search).get("open") || "diagnostics");
