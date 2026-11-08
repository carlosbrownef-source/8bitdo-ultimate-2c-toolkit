// SPDX-License-Identifier: GPL-3.0-or-later
// The Settings tab: the Home ring, and the settings the firmware keeps in its own record. A change goes to the controller
// at once and lasts until it's turned off, unless it's saved. Controls are built from SETTINGS_CARDS and the fields the app
// serves, which hold the ranges.
const percent = (v) => `${v} %`;
const stickRows = (side, bit) => [
  { field: `dz_${side}`, label: "Dead zone", kind: "range", format: percent },
  { field: `outer_${side}`, label: "Full movement at", kind: "range", format: percent },
  { field: `curve_${side}`, label: "Response", kind: "seg", format: (v) => ["Linear", "Precise", "Quick"][v] },
  { field: "invert", bit, label: "Invert left and right", kind: "bit" },
  { field: "invert", bit: bit + 1, label: "Invert up and down", kind: "bit" },
];
const SETTINGS_CARDS = [
  { title: "Sticks", wide: true, text: "The dead zone is how far a stick moves before it counts. Precise moves slowly near the centre for fine aiming, and Quick moves faster.", columns: [
    { heading: "Left stick", rows: stickRows("l", 0) }, { heading: "Right stick", rows: stickRows("r", 2) },
  ] },
  { title: "Triggers", wide: true, text: "How far a trigger moves before it starts to count, and where it reaches full.", columns: [
    { heading: "Left trigger", rows: [{ field: "lt_start", label: "Starts at", kind: "range", format: percent }, { field: "lt_end", label: "Full at", kind: "range", format: percent }] },
    { heading: "Right trigger", rows: [{ field: "rt_start", label: "Starts at", kind: "range", format: percent }, { field: "rt_end", label: "Full at", kind: "range", format: percent }] },
  ] },
  { title: "L4 and R4", wide: true, kind: "mapping", text: "Choose what each back button presses. Over Bluetooth, games don't see them unless you map them. Pressing L4 and R4 together changes the Home ring's brightness, and games also receive the buttons you mapped to them." },
  { title: "Vibration", text: "How strongly games make the controller vibrate, on the scale games use: the motors can't turn slower than about a fifth of their speed, so 25 % isn't a quarter of the strength. Battery alerts keep their own strength.", rows: [
    { field: "vibration", label: "Vibration from games", kind: "seg", format: (v) => `${v} %` },
  ] },
  { title: "Power", text: "The controller turns itself off when it's connected and nobody has used it for this long.", rows: [
    { field: "idle_min", label: "Turn off after", kind: "seg", format: (v) => `${v} min` },
    { field: "buzz", label: "Vibrate when connecting", kind: "toggle" },
  ] },
  { title: "Button remapping", wide: true, kind: "remap", text: "Choose what each button does, in every game. L4 and R4 keep pressing what you chose for them above. Home and the triggers can't be changed. If this leaves you stuck, Reset to defaults works without pressing any buttons on the controller." },
  { title: "Calibration", wide: true, kind: "calibration", text: "If a stick doesn't reach its full range or doesn't return to the centre, the controller can measure them again. This uses a function of its own, and the app doesn't send it anything." },
];
const CALIBRATION_STEPS = [
  "Connect the controller and leave the sticks alone.",
  "Hold − (Select), + (Start), LB and RB for 7 seconds, until a light blinks. Keep the sticks still for a moment longer.",
  "Move both sticks all around their range, and press both triggers fully.",
  "Press − (Select), + (Start), LB and RB together once more to save. The light stops blinking.",
];
const REMAP_NAMES = ["+ (Start)", "Left stick press", "Right stick press", "− (Select)", "X", "Y", "D-pad right", "D-pad left", "D-pad down", "D-pad up", "LB", "RB", "B", "A"];  // by bit, as printed on the controller
const REMAP_ORDER = [13, 12, 4, 5, 10, 11, 1, 2, 3, 0, 9, 8, 7, 6];
const MAP_BUTTONS = [["A", 13], ["B", 12], ["X", 4], ["Y", 5], ["LB", 10], ["RB", 11], ["LT", 14], ["RT", 15], ["Left stick press", 1], ["Right stick press", 2], ["− (Select)", 3], ["+ (Start)", 0], ["D-pad up", 9], ["D-pad down", 8], ["D-pad left", 7], ["D-pad right", 6]];

const SETTINGS_MISSING = "Controller settings isn't installed. Install it in the Firmware tab to change the sticks, triggers, buttons and vibration.";
let settingsData = null, settingsValues = {}, settingsDirty = false, settingsBusy = false, settingsMessage = "", settingsLoading = false, settingsRead = null;

function settingsAccess() {  // the reason the settings can't be changed right now, or null if they can
  const modes = st ? st.devices.map((d) => d.mode) : [];
  if (busy) return "Please wait until the task finishes.";
  if (modes.includes("boot")) return "These settings can't be changed in update mode. Turn the controller off and connect it by cable as usual.";
  if (!modes.some((m) => m === "cable" || m === "cable_360")) return "Connect the controller by cable to change these settings.";
  if (!fw) return "Reading the firmware…";
  if (fw.error) return fw.error;
  if (!fw.recipes || !fw.recipes.includes("settings")) return SETTINGS_MISSING;
  return null;
}

function settingsMount() {
  const fields = Object.fromEntries(settingsData.fields.map((f) => [f.name, f]));
  const box = $("settings-cards");
  box.replaceChildren(...SETTINGS_CARDS.map((card) => {
    const section = document.createElement("section");
    section.className = card.wide ? "cd set-wide" : "cd";
    section.innerHTML = `<h2></h2><p></p>`;
    section.querySelector("h2").textContent = card.title;
    section.querySelector("p").textContent = card.text;
    if (card.title === "Sticks") section.append(deadZoneRow());
    if (card.kind === "mapping") section.append(...[["L4", "l4"], ["R4", "r4"]].map(mappingRow));
    if (card.kind === "remap") {
      const grid = document.createElement("div");
      grid.className = "set-remap";
      grid.append(...REMAP_ORDER.map(remapRow));
      section.append(grid);
    }
    if (card.kind === "calibration") {
      const steps = document.createElement("ol");
      steps.className = "set-steps";
      steps.replaceChildren(...CALIBRATION_STEPS.map((t) => { const li = document.createElement("li"); li.textContent = t; return li; }));
      section.append(steps);
    }
    if (card.columns) {
      const cols = document.createElement("div");
      cols.className = "set-cols";
      card.columns.forEach((column) => {
        const box = document.createElement("div"), h = document.createElement("h3");
        h.textContent = column.heading;
        box.append(h, ...column.rows.map((row) => settingsRow(row, fields[row.field])));
        cols.append(box);
      });
      section.append(cols);
    } else if (card.rows) {
      card.rows.forEach((row) => section.append(settingsRow(row, fields[row.field])));
    }
    return section;
  }));
}

function deadZoneRow() {
  const line = document.createElement("div"), label = document.createElement("span"), t = document.createElement("label"), input = document.createElement("input"), sw = document.createElement("span");
  line.className = "set-row";
  label.textContent = "Turn off the dead zones. Holding − (Select) and + (Start) together for about 4 seconds on the controller does the same.";
  t.className = "set-toggle"; sw.className = "sw";
  input.type = "checkbox"; input.id = "dead-zone-off";
  input.setAttribute("aria-label", "Turn off the dead zones");
  input.onchange = () => settingsSwitch(input.checked);
  t.append(input, sw);
  line.append(label, t);
  return line;
}

function mappingRow([name, slot]) {
  const line = document.createElement("div"), label = document.createElement("span"), box = document.createElement("div");
  line.className = "set-row set-map";
  label.textContent = name;
  box.className = "set-chips";
  MAP_BUTTONS.forEach(([text, bit]) => {
    const b = document.createElement("button");
    b.className = "sec small";
    b.textContent = text; b.dataset.slot = slot; b.dataset.bit = bit;
    b.onclick = () => settingsMap(slot, settingsData.mapping[slot] ^ (1 << bit));
    box.append(b);
  });
  line.append(label, box);
  return line;
}

function remapRow(bit) {
  const line = document.createElement("div"), label = document.createElement("span"), pick = document.createElement("select"), name = `remap_${bit}`;
  line.className = "set-row";
  label.textContent = REMAP_NAMES[bit];
  pick.dataset.field = name;
  pick.setAttribute("aria-label", `What ${REMAP_NAMES[bit]} does`);
  REMAP_ORDER.forEach((b) => { const o = document.createElement("option"); o.value = b; o.textContent = REMAP_NAMES[b]; pick.append(o); });
  const nothing = document.createElement("option");
  nothing.value = 255; nothing.textContent = "Nothing";
  pick.append(nothing);
  pick.onchange = () => settingsChange(name, +pick.value);
  line.append(label, pick);
  return line;
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
  } else if (row.kind === "range") {
    const box = document.createElement("div"), input = document.createElement("input"), out = document.createElement("output");
    box.className = "set-range";
    input.type = "range"; input.min = field.low; input.max = field.high; input.dataset.field = row.field;
    input.setAttribute("aria-label", row.label);
    input.oninput = () => { out.textContent = row.format(+input.value); };  // the controller hears about it when it's let go
    input.onchange = () => settingsChange(row.field, +input.value);
    input.paintOut = (v) => { out.textContent = row.format(v); };
    box.append(input, out);
    line.append(box);
  } else if (row.kind === "toggle" || row.kind === "bit") {
    const t = document.createElement("label"), input = document.createElement("input"), sw = document.createElement("span");
    t.className = "set-toggle"; sw.className = "sw";
    input.type = "checkbox"; input.dataset.field = row.field;
    input.setAttribute("aria-label", row.label);
    if (row.kind === "bit") {
      input.dataset.bit = row.bit;
      input.onchange = () => settingsChange(row.field, settingsValues[row.field] ^ (1 << row.bit));
    } else {
      input.onchange = () => settingsChange(row.field, input.checked ? 1 : 0);
    }
    t.append(input, sw);
    line.append(t);
  }
  return line;
}

function settingsPaint() {
  document.querySelectorAll("#settings-cards [data-field]").forEach((c) => {
    const v = settingsValues[c.dataset.field];
    if (c.classList.contains("seg")) {
      c.querySelectorAll("button").forEach((b) => { setOn(b, +b.dataset.value === v); b.disabled = settingsBusy; });
    } else if (c.type === "checkbox") {
      c.checked = c.dataset.bit === undefined ? !!v : !!(v >> +c.dataset.bit & 1); c.disabled = settingsBusy;
    } else if (c.tagName === "SELECT") {
      c.value = v; c.dataset.now = v; c.disabled = settingsBusy;
    } else if (c.type === "range") {
      c.value = v; c.setAttribute("value", v); c.paintOut(v); c.disabled = settingsBusy;
    }
  });
  const off = $("dead-zone-off");
  off.checked = settingsData.dead_zone_off; off.disabled = settingsBusy;
  document.querySelectorAll("#settings-cards [data-slot]").forEach((b) => {
    setOn(b, !!(settingsData.mapping[b.dataset.slot] >> +b.dataset.bit & 1)); b.disabled = settingsBusy;
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
  if (data.available) {
    if (settingsDirty) settingsMessage = "The changes you hadn't saved were discarded, and the controller is back on what it has saved.";
    settingsValues = { ...data.values }; settingsDirty = false; settingsMount();
  }
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

async function settingsMap(slot, mask) {
  if (settingsBusy) return;
  if (await settingsPost({ mapping: { slot, mask } })) { settingsData.mapping[slot] = mask; settingsDirty = true; }
  settingsPaint();
}

async function settingsSwitch(off) {
  if (settingsBusy) return;
  if (await settingsPost({ dead_zone_off: off })) { settingsData.dead_zone_off = off; settingsDirty = true; }
  settingsPaint();
}

async function settingsSave() {
  if (settingsBusy) return;
  if (await settingsPost({ save: true, values: settingsValues, kept_mapping: settingsData.mapping, kept_dead_zone_off: settingsData.dead_zone_off })) {
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
    settingsData.mapping = { r4: 0, l4: 0 };
    settingsData.dead_zone_off = false;
    settingsDirty = false;
    settingsMessage = "The controller is back on the default settings.";
  }
  settingsPaint();
}

function settingsLive(e) {  // what macOS reports, to see a change's effect straight away
  const place = (el, x, y) => { el.style.transform = `translate(${x * 24}px, ${-y * 24}px)`; };
  place($("live-left"), e.lx, e.ly); place($("live-right"), e.rx, e.ry);
  $("live-lt").style.width = `${Math.round(e.lt * 100)}%`; $("live-rt").style.width = `${Math.round(e.rt * 100)}%`;
  $("live-note").hidden = true;
}

function settingsShow() {
  const b = bridge();
  $("live-note").hidden = false;
  $("live-note").textContent = b ? "Move a stick or press a trigger to see it here. If nothing moves, macOS isn't seeing the controller by cable as a game controller, which is what the Xbox 360 tweak is for." : "This live view only works in the Mac app. The settings work anyway.";
  if (b) b.postMessage({ op: "start" });
}

function settingsHide() {
  const b = bridge();
  if (b) b.postMessage({ op: "stop" });
}

function settingsRender() {
  ringRender();
  if (fw !== settingsRead) { settingsRead = fw; settingsData = null; if (!settingsDirty) settingsMessage = ""; }  // each read of the firmware can mean another controller
  const reason = settingsAccess();
  if (!reason && !settingsData && !settingsLoading && tab === "settings") settingsLoad();
  const ready = !reason && settingsData && settingsData.available;
  $("settings-note").textContent = reason || (settingsData && settingsData.note) || (ready ? "" : "Reading the settings…");
  $("settings-empty").hidden = !!ready;
  $("settings-retry").hidden = !(!reason && settingsData && !settingsData.available);
  $("settings-goto").hidden = $("settings-note").textContent !== SETTINGS_MISSING;
  $("settings-cards").hidden = $("settings-actions").hidden = $("live-card").hidden = !ready;
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
  document.querySelectorAll("[data-live]").forEach((b) => { b.disabled = off; setOn(b, +b.dataset.live === ringLevel); });
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
  $("settings-retry").onclick = () => { settingsData = null; settingsRender(); };
  $("settings-goto").onclick = () => showTab("firmware");
});
