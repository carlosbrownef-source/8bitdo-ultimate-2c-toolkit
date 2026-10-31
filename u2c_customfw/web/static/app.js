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
const log = (text) => { const el = $("log"); el.textContent += text + "\n"; el.scrollTop = el.scrollHeight; };
const bar = (label, done, total) => {
  const p = Math.min(100, Math.floor((done * 100) / Math.max(total, 1) / 10) * 10);
  $("bar").textContent = `[${"#".repeat(p / 10)}${"-".repeat(10 - p / 10)}] ${String(p).padStart(3)} % ${label}`;
};
let busy = false;
const setBusy = (b) => { busy = b; document.querySelectorAll("button").forEach((x) => { if (x.id !== "confirm-no" && x.id !== "confirm-yes") x.disabled = b; }); };

async function runJob(path, body) {
  $("log").textContent = ""; $("bar").textContent = "starting…"; setBusy(true);
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
        if (e.type === "log") log(e.text);
        else if (e.type === "progress") bar(e.label, e.done, e.total);
        else if (e.type === "done") { log("Done."); }
        else if (e.type === "error") { log("Stopped: " + e.message); $("bar").textContent = "stopped"; }
      }
    }
  } catch (e) { log("Error: " + e.message); $("bar").textContent = "stopped"; }
  setBusy(false); refresh();
}

function confirmWrite(what) {
  return new Promise((resolve) => {
    $("confirm-what").textContent = what;
    const d = $("confirm"), done = (v) => { d.close(); resolve(v); };
    $("confirm-yes").onclick = () => done(true); $("confirm-no").onclick = () => done(false);
    d.showModal();
  });
}

const tweaks = () => [...document.querySelectorAll(".tweak:checked")].map((x) => x.value);
function syncTweaks() {
  const xbox = document.querySelector('.tweak[value="bt_xbox"]'), rumble = document.querySelector('.tweak[value="bt_rumble"]');
  rumble.disabled = !xbox.checked; if (!xbox.checked) rumble.checked = false;
  rumble.parentElement.classList.toggle("off", !xbox.checked);
}
const base = () => document.querySelector('input[name="base"]:checked').value;

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
  try {
    const s = await api("GET", "/api/state");
    $("version").textContent = "v" + s.version;
    $("disclaimer").hidden = s.accepted; $("app").hidden = !s.accepted; renderDisclaimer(s.disclaimer);
    $("devices").innerHTML = "";
    if (!s.devices.length) $("devices").innerHTML = "<li>No controller found. Plug it in by cable, or put it in boot mode.</li>";
    for (const d of s.devices) {
      const li = document.createElement("li"); li.textContent = `${d.mode}: ${d.name || ""}`; if (d.mode === "error") li.className = "err"; $("devices").append(li);
    }
  } catch (e) { $("devices").textContent = "Cannot reach the app: " + e.message; return; }
  showFirmware();
}

let fwSeq = 0;
async function showFirmware() {  // reads the controller's firmware (read-only); skipped while a job runs
  const el = $("firmware"), mine = ++fwSeq;
  if (busy) return;
  el.textContent = "Reading the controller's firmware…";
  try {
    const f = await api("GET", "/api/firmware");
    if (mine !== fwSeq) return;
    el.textContent = "";
    const strong = document.createElement("strong");
    if (f.error || f.note) { el.textContent = f.error || f.note; return; }
    el.append("Firmware: ");
    if (!f.known) { strong.className = "bad"; strong.textContent = "unknown (not stock v1.09 or one of ours): use Diagnose and restore"; el.append(strong); return; }
    strong.className = "ok"; strong.textContent = "stock v1.09"; el.append(strong);
    el.append(f.titles.length ? " with: " + f.titles.join(", ") : ", no tweaks applied");
  } catch (e) { if (mine === fwSeq) el.textContent = ""; }
}

$("accept").onclick = async () => { await api("POST", "/api/accept"); refresh(); };
$("refresh").onclick = refresh;
$("backup").onclick = () => runJob("/api/backup");
document.querySelectorAll(".tweak").forEach((x) => (x.onchange = syncTweaks));
$("patch-dry").onclick = () => runJob("/api/patch", { tweaks: tweaks(), base: base(), write: false });
$("patch-write").onclick = async () => {
  if (!tweaks().length) return log("Choose at least one tweak.");
  if (await confirmWrite("Patch with: " + tweaks().join(", ") + ".")) runJob("/api/patch", { tweaks: tweaks(), base: base(), write: true });
};
$("restore-backup-dry").onclick = () => runJob("/api/restore", { source: "backup", write: false });
$("restore-stock-dry").onclick = () => runJob("/api/restore", { source: "stock", write: false });
$("restore-backup").onclick = async () => { if (await confirmWrite("Put back your backup.")) runJob("/api/restore", { source: "backup", write: true }); };
$("restore-stock").onclick = async () => { if (await confirmWrite("Put back 8BitDo's firmware 1.09.")) runJob("/api/restore", { source: "stock", write: true }); };
$("report").onclick = async () => { const r = await api("POST", "/api/report"); $("report-text").hidden = false; $("report-text").textContent = r.text; };
syncTweaks(); refresh();
