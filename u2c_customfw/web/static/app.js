// SPDX-License-Identifier: GPL-3.0-or-later
const token = new URLSearchParams(location.search).get("token") || "";
const $ = (id) => document.getElementById(id);
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
const stick = (x, y) => `<circle cx="${x}" cy="${y}" r="19" fill="#1c2026"/><circle cx="${x}" cy="${y}" r="13.5" fill="#4b525c"/><circle cx="${x}" cy="${y}" r="9" fill="#424851"/>`;
const face = (x, y, t) => `<circle cx="${x}" cy="${y}" r="8.6" fill="#4b525c"/><text x="${x}" y="${y + 2.9}" text-anchor="middle" font-size="8.5" font-weight="600" fill="#b9c0c9" font-family="-apple-system,sans-serif">${t}</text>`;
const pad = (led, dim) => `<svg viewBox="0 0 300 172" fill="none" role="img" aria-label="Controller"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a4049"/><stop offset="1" stop-color="#2a2f36"/></linearGradient></defs>
<path d="M66 32c7-11 29-14 41-9M234 32c-7-11-29-14-41-9" stroke="#454b54" stroke-width="9" stroke-linecap="round"/>
<path d="M105 24L195 24C217.5 22 235.5 26 245.4 36C259.8 52 267 92 265.2 128C263.4 160 241.8 170 231 156C223.8 146 216.6 132 198.6 128L101.4 128C83.4 132 76.2 146 69 156C58.2 170 36.6 160 34.8 128C33 92 40.2 52 54.6 36C64.5 26 82.5 22 105 24Z" fill="url(#g)" stroke="#4d545e" stroke-width="1.5" ${dim ? 'stroke-dasharray="5 4"' : ""}/>
${stick(81, 62)}${stick(182, 100)}
<circle cx="118" cy="100" r="20" fill="#30353d"/><path d="M112.5 85h11v9.5h9.5v11h-9.5v9.5h-11v-9.5h-9.5v-11h9.5z" fill="#4b525c"/>
${face(215, 43, "Y")}${face(198, 60, "X")}${face(232, 60, "B")}${face(215, 77, "A")}
<circle cx="120" cy="40" r="4.5" fill="#454b54"/><circle cx="180" cy="40" r="4.5" fill="#454b54"/><circle cx="135" cy="59" r="4.5" fill="#454b54"/><circle cx="165" cy="59" r="4.5" fill="#454b54"/><circle cx="150" cy="59" r="1.6" fill="#1c2026"/>
<circle cx="150" cy="40" r="8" fill="#30353d" stroke="${led || "#4d545e"}" stroke-width="2.4"/>${led ? `<circle cx="150" cy="40" r="13" stroke="${led}" stroke-width="5" opacity=".18"/>` : ""}
</svg>`;

const CONTROLLER = ["cable", "cable_360", "boot"];
let st = null, fw = null, reading = false, busy = false, base = "backup";

const tweakBoxes = () => [...document.querySelectorAll(".tweak")];
const tweaks = () => tweakBoxes().filter((x) => x.checked).map((x) => x.value);
const tweakTitles = () => tweakBoxes().filter((x) => x.checked).map((x) => x.parentElement.lastElementChild.firstChild.textContent);

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
  else if (reading) title = "Reading the firmware…";
  else if (fw && fw.error) [cls, title, note] = ["bad", "Can't read the firmware", fw.error];
  else if (fw && fw.note) note = fw.note;
  else if (fw && fw.known) {
    title = `Firmware 1.09 — ${fw.recipes.length ? "modified" : "unmodified"}`;
    note = fw.version_from && fw.version_from !== "unknown" ? "Version read from the controller" : "";
    chips = fw.tweaks;
  } else if (fw && fw.version && fw.version.toFixed(2) !== "1.09")
    [cls, title, note] = ["bad", `Firmware ${fw.version.toFixed(2)} — not supported`, "This app only works with firmware 1.09. Update the controller with 8BitDo's own updater first, or restore your backup."];
  else if (fw) [cls, title, note] = ["bad", "Unknown firmware", "It doesn't match the original firmware 1.09, with or without the tweaks. Restore can repair it."];

  const badge = ctrl ? `${boot ? "Update mode" : "Connected by cable"} · 8BitDo Ultimate 2C Wireless`
    : dongle ? "2.4 GHz dongle" : bt ? "Connected over Bluetooth · 8BitDo Ultimate 2C Wireless" : "Not connected";
  $("hero").className = "hero " + cls;
  $("badge").className = "badge " + (cls === "bad" ? "bad" : boot ? "isboot" : ctrl || bt ? "ok" : "");
  $("badge-text").textContent = badge;
  $("fw-title").textContent = title;
  $("fw-note").textContent = note;
  const led = cls === "none" ? null : cls === "bad" ? "#e8695b" : boot ? "#ffffff" : getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  $("pic").innerHTML = pad(led, cls === "none");
  const box = $("chips"); box.textContent = ""; box.hidden = !chips;
  for (const t of chips || []) {
    const c = document.createElement("span"); c.className = "chip" + (t.on ? " on" : "");
    c.innerHTML = t.on ? ICON.ok : ICON.dash; c.append(t.title); box.append(c);
  }
}

function render() {
  const devs = st ? st.devices : [];
  const ctrl = devs.find((d) => CONTROLLER.includes(d.mode)), boot = !!ctrl && ctrl.mode === "boot";
  const backed = !!st && st.backups.length > 0, off = busy || reading, patchable = boot && backed && tweaks().length > 0 && !(fw && fw.known === false);
  hero(devs, ctrl, boot);

  $("last-backup").textContent = st ? lastBackup(st.backups) : "";
  const pre = (el, ok, yes, no) => { el.className = ok ? "ok" : ""; el.innerHTML = ok ? ICON.ok : ICON.no; el.append(ok ? yes : no); };
  pre($("pre-backup"), backed, "Backup saved", "No backup yet");
  pre($("pre-boot"), boot, "In update mode", "Not in update mode");
  $("boot-box").className = "boot" + (boot ? " ok" : "");
  $("boot-icon").innerHTML = boot ? ICON.ok.replace("<svg", '<svg width="20"') : ICON.plug;
  $("boot-title").textContent = boot ? "The controller is in update mode" : "Update mode";

  const xbox = tweakBoxes().find((x) => x.value === "bt_xbox"), rumble = tweakBoxes().find((x) => x.value === "bt_rumble");
  if (!xbox.checked) rumble.checked = false;
  tweakBoxes().forEach((x) => { x.disabled = busy || (x === rumble && !xbox.checked); x.parentElement.classList.toggle("off", x.disabled); });
  $("choose-one").hidden = tweaks().length > 0;

  const can = { backup: !!ctrl, "patch-dry": patchable, "patch-write": patchable,
    "restore-backup-dry": boot && backed, "restore-backup": boot && backed, "restore-stock-dry": boot && backed, "restore-stock": boot && backed,
    "force-open": boot && backed, "report-open": true, refresh: true };
  for (const [id, ok] of Object.entries(can)) $(id).disabled = off || !ok;
  $("force-zone").classList.toggle("hot", !!fw && fw.known === false && !fw.version && !fw.error);
}

const STEPS = { "pass 1": [0, 50], "pass 2": [50, 50], write: [0, 100] };  // progress labels from the core
const setPct = (p) => { $("prog-bar").style.width = p + "%"; $("pc").textContent = p + " %"; };
function line(text, bad) {
  const el = $("log"), s = document.createElement("span");
  if (bad) s.className = "e";
  s.textContent = text + "\n"; el.append(s); el.scrollTop = el.scrollHeight;
}

async function runJob(label, path, body) {
  busy = true; render();
  $("log").textContent = ""; $("log").hidden = false; $("log-toggle").hidden = false; $("log-toggle").textContent = "Hide log ▾";
  $("dock").className = "dock run"; $("dock-status").textContent = label;
  $("idle").hidden = true; $("prog").hidden = $("pc").hidden = false; setPct(0);
  let ok = false;
  try {
    await api("POST", path, body);
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
        else if (e.type === "done") ok = true;
        else if (e.type === "error") line("Stopped: " + e.message, true);
      }
    }
  } catch (e) { line("Stopped: " + e.message, true); }
  $("dock").className = "dock " + (ok ? "done" : "err"); $("dock-status").textContent = ok ? "Done" : "Stopped";
  if (ok) setPct(100);
  busy = false; refresh();
}

function ask(title, text, chips, yes) {
  $("confirm-title").textContent = title; $("confirm-text").textContent = text; $("confirm-yes").textContent = yes;
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

async function refresh() {
  try { st = await api("GET", "/api/state"); }
  catch (e) { st = { devices: [{ mode: "error", name: "Can't reach the app: " + e.message }], backups: [] }; fw = null; return render(); }
  $("version").textContent = "v" + st.version;
  renderDisclaimer(st.disclaimer);
  if (!st.accepted && !$("disclaimer").open) $("disclaimer").showModal();
  fw = null; render(); readFirmware();
}

let fwSeq = 0;
async function readFirmware() {  // read-only; skipped while a job runs, and the job buttons wait for it
  if (busy || !st.devices.some((d) => CONTROLLER.includes(d.mode) || d.mode === "dongle" || d.mode.startsWith("bluetooth"))) return;
  const mine = ++fwSeq; reading = true; render();
  let f;
  try { f = await api("GET", "/api/firmware"); } catch (e) { f = { error: e.message }; }
  if (mine !== fwSeq) return;
  fw = f; reading = false; render();
}

document.querySelectorAll("[data-icon]").forEach((e) => (e.innerHTML = ICON[e.dataset.icon]));
$("disclaimer").oncancel = (e) => e.preventDefault();
$("accept").onclick = async () => { await api("POST", "/api/accept"); $("disclaimer").close(); refresh(); };
$("refresh").onclick = refresh;
$("help-open").onclick = () => $("help").showModal();
$("help-close").onclick = () => $("help").close();
tweakBoxes().forEach((x) => (x.onchange = render));
document.querySelectorAll("[data-base]").forEach((b) => (b.onclick = () => {
  base = b.dataset.base; document.querySelectorAll("[data-base]").forEach((x) => x.classList.toggle("on", x === b));
}));
$("log-toggle").onclick = () => { const l = $("log"); l.hidden = !l.hidden; $("log-toggle").textContent = l.hidden ? "Show log ▴" : "Hide log ▾"; };

$("backup").onclick = () => runJob("Backing up", "/api/backup");
$("patch-dry").onclick = () => runJob("Checking", "/api/patch", { tweaks: tweaks(), base, write: false });
$("patch-write").onclick = async () => {
  if (await ask("Install these tweaks?", "This changes the controller's firmware and voids its warranty.", tweakTitles(), "Install"))
    runJob("Installing", "/api/patch", { tweaks: tweaks(), base, write: true });
};
$("restore-backup-dry").onclick = () => runJob("Checking", "/api/restore", { source: "backup", write: false });
$("restore-stock-dry").onclick = () => runJob("Checking", "/api/restore", { source: "stock", write: false });
$("restore-backup").onclick = async () => {
  if (await ask("Restore your backup?", "This rewrites the controller's firmware with the one in your backup.", [], "Restore"))
    runJob("Restoring", "/api/restore", { source: "backup", write: true });
};
$("restore-stock").onclick = async () => {
  if (await ask("Restore the original firmware 1.09?", "This replaces the controller's firmware with 8BitDo's original 1.09, downloaded from 8BitDo.", [], "Restore"))
    runJob("Restoring", "/api/restore", { source: "stock", write: true });
};
$("force-open").onclick = () => {
  const d = $("force"), tick = $("force-understand"), yes = $("force-yes");
  tick.checked = false; yes.disabled = true;
  tick.onchange = () => { yes.disabled = !tick.checked; };
  $("force-no").onclick = () => d.close();
  yes.onclick = () => { d.close(); runJob("Installing", "/api/restore", { source: "stock", write: true, force_unknown: true }); };
  d.showModal();
};
$("report-open").onclick = async () => {
  try { $("report-text").textContent = (await api("POST", "/api/report")).text; } catch (e) { $("report-text").textContent = e.message; }
  $("report").showModal();
};
$("report-copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("report-text").textContent); $("report-copy").textContent = "Copied"; }
  catch (e) { getSelection().selectAllChildren($("report-text")); }  // then ⌘C
};
$("report-close").onclick = () => { $("report").close(); $("report-copy").textContent = "Copy"; };
render(); refresh();
