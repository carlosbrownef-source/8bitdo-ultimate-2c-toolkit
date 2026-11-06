// SPDX-License-Identifier: GPL-3.0-or-later
// The Settings tab: the Home ring, and the settings the firmware keeps in its own record. A change goes to the controller
// at once and lasts until it's turned off, unless it's saved. Controls are built from SETTINGS_CARDS and the fields the app
// serves, which hold the ranges.
const SETTINGS_CARDS = [
  { title: "Vibration", text: "How strongly games make the controller vibrate. Battery alerts keep their own strength.", rows: [
    { field: "vibration", label: "Vibration from games", kind: "seg", format: (v) => `${v} %` },
  ] },
  { title: "Power", text: "The controller turns itself off when it's connected and nobody has used it for this long.", rows: [
    { field: "idle_min", label: "Turn off after", kind: "seg", format: (v) => `${v} min` },
    { field: "buzz", label: "Vibrate when connecting", kind: "toggle" },
  ] },
];

let settingsData = null, settingsValues = {}, settingsDirty = false, settingsBusy = false, settingsMessage = "", settingsLoading = false, settingsRead = null;

function settingsAccess() {  // the reason the settings can't be changed right now, or null if they can
  const modes = st ? st.devices.map((d) => d.mode) : [];
  if (busy) return "Please wait until the task finishes.";
  if (modes.includes("boot")) return "These settings can't be changed in update mode. Turn the controller off and connect it by cable as usual.";
  if (!modes.some((m) => m === "cable" || m === "cable_360")) return "Connect the controller by cable to change these settings.";
  if (!fw) return "Reading the firmware…";
  if (!fw.recipes || !fw.recipes.includes("settings")) return "To change these settings, install Controller settings in the Firmware tab.";
  return null;
}

function settingsMount() {
  const fields = Object.fromEntries(settingsData.fields.map((f) => [f.name, f]));
  const box = $("settings-cards");
  box.replaceChildren(...SETTINGS_CARDS.map((card) => {
    const section = document.createElement("section");
    section.className = "cd";
    section.innerHTML = `<h2></h2><p></p>`;
    section.querySelector("h2").textContent = card.title;
    section.querySelector("p").textContent = card.text;
    card.rows.forEach((row) => section.append(settingsRow(row, fields[row.field])));
    return section;
  }));
}

function settingsRow(row, field) {
  const line = document.createElement("div");
  line.className = "set-row";
  const label = document.createElement("span");
  label.textContent = row.label;
  line.append(label);
  if (row.kind === "seg") {
    const seg = document.createElement("div");
    seg.className = "seg";
    seg.dataset.field = row.field;
    (field.choices || Array.from({ length: field.high - field.low + 1 }, (_, i) => field.low + i)).forEach((v) => {
      const b = document.createElement("button");
      b.dataset.value = v;
      b.textContent = row.format ? row.format(v) : v;
      b.onclick = () => settingsChange(row.field, v);
      seg.append(b);
    });
    line.append(seg);
  } else if (row.kind === "toggle") {
    const t = document.createElement("label");
    t.className = "set-toggle";
    t.innerHTML = `<input type="checkbox" data-field="${row.field}"><span class="sw"></span>`;
    t.querySelector("input").onchange = (e) => settingsChange(row.field, e.target.checked ? 1 : 0);
    line.append(t);
  }
  return line;
}

function settingsPaint() {
  document.querySelectorAll("#settings-cards [data-field]").forEach((c) => {
    const v = settingsValues[c.dataset.field];
    if (c.classList.contains("seg")) {
      c.querySelectorAll("button").forEach((b) => { b.classList.toggle("on", +b.dataset.value === v); b.disabled = settingsBusy; });
    } else if (c.type === "checkbox") {
      c.checked = !!v; c.disabled = settingsBusy;
    }
  });
  $("settings-save").disabled = $("settings-reset").disabled = settingsBusy;
  $("settings-unsaved").hidden = !settingsDirty;
  $("settings-message").textContent = settingsMessage;
}

async function settingsLoad() {
  settingsLoading = true;
  let data;
  try { data = await api("GET", "/api/settings"); } catch (e) { data = { available: false, note: e.message }; }
  settingsLoading = false;
  settingsData = data;
  if (data.available) { settingsValues = { ...data.values }; settingsDirty = false; settingsMount(); }
  settingsRender();
}

async function settingsPost(body) {  // true if it went well; the message says why if not
  settingsBusy = true; settingsMessage = ""; settingsPaint();
  try { const answer = await api("POST", "/api/settings", body); settingsBusy = false; return answer; }
  catch (e) { settingsBusy = false; settingsMessage = e.message; return null; }
}

async function settingsChange(name, value) {
  if (settingsBusy) return;
  const before = settingsValues[name];
  settingsValues[name] = value;
  if (await settingsPost({ set: { [name]: value } })) settingsDirty = true;
  else settingsValues[name] = before;
  settingsPaint();
}

async function settingsSave() {
  if (settingsBusy) return;
  if (await settingsPost({ save: true, values: settingsValues })) {
    settingsDirty = false;
    settingsMessage = "Saved. The controller keeps these settings when you turn it off.";
  }
  settingsPaint();
}

async function settingsReset() {
  if (settingsBusy || !await ask("Go back to the default settings?", "This replaces the settings saved in the controller. The firmware stays as it is.", [], "Reset")) return;
  const answer = await settingsPost({ reset: true });
  if (answer) {
    settingsValues = { ...answer.values };
    settingsDirty = false;
    settingsMessage = "The controller is back on the default settings.";
  }
  settingsPaint();
}

function settingsRender() {
  ringRender();
  if (fw !== settingsRead) { settingsRead = fw; settingsData = null; settingsMessage = ""; }  // each read of the firmware can mean another controller
  const reason = settingsAccess();
  if (!reason && !settingsData && !settingsLoading && tab === "settings") settingsLoad();
  const ready = !reason && settingsData && settingsData.available;
  $("settings-note").textContent = reason || (settingsData && settingsData.note) || (ready ? "" : "Reading the settings…");
  $("settings-note").hidden = !!ready;
  $("settings-cards").hidden = $("settings-actions").hidden = !ready;
  if (ready) settingsPaint();
}

let ringLevel = null, ringBusy = false, ringId = 0, ringMessage = "", ringTimer = null, ringAsked = null, ringRead = null, ringVia = null;

function ringAccess() {  // how the card can reach the controller, or why it can't
  const modes = st ? st.devices.map((d) => d.mode) : [];
  if (busy) return { note: "Please wait until the task finishes." };
  if (modes.some((m) => m === "cable" || m === "cable_360")) {
    if (!fw) return { note: "Reading the firmware…" };
    if (fw.outdated) return { note: "This firmware has the Home ring from an earlier version. Install the tweaks again to change it here." };
    if (fw.ring_level === undefined || fw.ring_level === null) return { note: "To change the ring here, install a Home ring brightness in the Firmware tab." };
    return { via: "cable" };
  }
  if (modes.includes("bluetooth_xbox")) return bridge() ? { via: "bluetooth" } : { note: "Over Bluetooth, this only works in the Mac app." };
  return { note: "Connect the controller by Bluetooth or cable." };
}

function ringRender() {
  const access = ringAccess(), off = !access.via || ringBusy;
  if (fw && fw !== ringRead) { ringRead = fw; ringLevel = fw.ring_level === undefined ? null : fw.ring_level; }  // each read says what the ring starts at
  document.querySelectorAll("[data-live]").forEach((b) => { b.disabled = off; b.classList.toggle("on", +b.dataset.live === ringLevel); });
  $("ring-save").disabled = off;
  $("ring-note").textContent = access.note || ringMessage || (access.via === "bluetooth"
    ? "This needs the Home ring and Rumble over Bluetooth tweaks. A change lasts until you turn the controller off, unless you save it."
    : "A change lasts until you turn the controller off, unless you save it.");
}

function ringDone(error, level, save) {
  clearTimeout(ringTimer);
  ringBusy = false; ringAsked = null;
  if (error) ringMessage = error;
  else {
    if (level !== null) ringLevel = level;
    const ifTweaks = "If the Home ring and Rumble over Bluetooth tweaks are installed";
    if (ringVia === "bluetooth") ringMessage = save ? `Sent. ${ifTweaks}, the controller keeps this level when you turn it off.` : `Sent. ${ifTweaks}, the ring changes at once, until you turn the controller off or save it.`;
    else ringMessage = save ? "Saved. The controller keeps this level when you turn it off." : "Sent. Save it if you want to keep it after turning the controller off.";
  }
  ringRender();
}

async function ringSend(level, save) {
  const access = ringAccess();
  if (!access.via || ringBusy) return;
  ringBusy = true; ringMessage = ""; ringVia = access.via; ringRender();
  if (access.via === "cable") {
    let error = null;
    try { await api("POST", "/api/ring", level === null ? { save: true } : { level }); } catch (e) { error = e.message; }
    return ringDone(error, level, save);
  }
  ringAsked = { id: ++ringId, level, save };
  ringTimer = setTimeout(() => ringDone("No answer from the app.", level, save), RESULT_TIMEOUT_MS);
  bridge().postMessage({ op: "ring", level: level === null ? 255 : level, save, id: ringId });
}

addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-live]").forEach((b) => (b.onclick = () => ringSend(+b.dataset.live, false)));
  document.getElementById("ring-save").onclick = () => ringSend(null, true);
});

addEventListener("DOMContentLoaded", () => {
  $("settings-save").onclick = settingsSave;
  $("settings-reset").onclick = settingsReset;
});
