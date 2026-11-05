// SPDX-License-Identifier: GPL-3.0-or-later
// The controller test: shows what macOS's GameController reports, through the Mac app's native bridge
// (macos/Diagnostics.swift). It sends the bridge {op} messages and receives window.u2cDiagnostics(event).
const CONTROLS = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "L3", "R3", "View", "Menu", "Home", "Up", "Down", "Left", "Right", "LS", "RS"];
const STICK_SEEN = 0.5, TRIGGER_SEEN = 0.1, STICK_TRAVEL = 7, RESULT_TIMEOUT_MS = 3000, ACCENT = "#3fc8b4";
const IDLE_LINE = "Vibrates for under a second. Nothing is written to the controller.";

let testVisible = false, testConnected = null, testState = null, testSeen = new Set(), testName = null, testMounted = null, testPending = null, testTimer = null, testId = 0;
const bridge = () => window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.diagnostics;

function clearPending() {
  clearTimeout(testTimer);
  testPending = null;
}

function diagnosticsShow() {
  clearPending();
  testVisible = true; testState = null; testConnected = null; testName = null; testMounted = null; testSeen = new Set();
  const b = bridge();
  if (b) b.postMessage({ op: "start" });
  diagnosticsRender();
  if (!busy && !refreshing) refresh();  // the controller was probably reconnected since the last look, for example after installing
}

function diagnosticsHide() {
  clearPending();
  testVisible = false;
  const b = bridge();
  if (b) b.postMessage({ op: "stop" });
}

function diagnosticsSummary() {
  if (!testState || !testState.connected) return null;
  return { name: testState.name, category: testState.category, localities: testState.localities };
}

function testMode() {
  if (!bridge()) return "web";
  if (busy) return "busy";
  if (st && st.devices.some((d) => d.mode === "boot")) return "boot";
  if (!testState || !testState.connected) return "none";
  if (!testState.extended) return "noext";
  if (!testState.foreground) return "background";
  return "live";
}

const TEST_MESSAGES = {
  web: "The controller test is only available in the Mac app. Everything else in this tab works here.",
  busy: "The controller test is unavailable while a task is running.",
  boot: "The controller test can't run in update mode. Disconnect the controller and connect it again by Bluetooth or cable.",
  none: "No controller found. Connect the controller by Bluetooth or cable to test it.",
  noext: "macOS sees this controller, but not as a standard gamepad, so its controls can't be tested here.",
  background: "The controller test is paused, because macOS only sends controller input to the app in front.",
};

function diagnosticsRender() {
  const body = $("test-body");
  if (!body || !testVisible) return;
  const mode = testMode();
  const key = mode === "live" ? `live:${testState.name}:${testState.category}:${testState.localities.join()}:${directLine()}` : mode;
  if (key === testMounted) return;
  testMounted = key;
  if (mode !== "live") {
    body.innerHTML = `<div class="test"><div class="test-pic dimmed">${pad(null, false, "test-g")}</div><div class="boot"><div id="test-message"></div></div></div>`;
    $("test-message").textContent = TEST_MESSAGES[mode];
    return;
  }
  mountLive(body);
}

const directAvailable = () => !!st && st.devices.some((d) => d.mode === "bluetooth_xbox");

const directLine = () => directAvailable() ? IDLE_LINE
  : st && st.devices.some((d) => d.mode === "bluetooth") ? "The direct report needs the Xbox Series X|S controller tweak."
  : "The direct report only works over Bluetooth.";

function vibrationText(localities) {
  if (!localities.length) return "Not available";
  return localities.includes("left") && localities.includes("right") ? "Available, also on the left and right sides separately" : "Available";
}

function mountLive(body) {
  const s = testState, has = (l) => s.localities.includes(l), direct = directAvailable();
  const button = (op, label, ok) => `<button class="sec small" data-op="${op}" data-was="${ok ? "" : "1"}"${ok && !testPending ? "" : " disabled"}>${label}</button>`;
  body.innerHTML = `<div class="test"><div class="test-pic" id="test-pic">${pad(ACCENT, false, "test-g")}</div><div>
    <dl class="rows"><dt>macOS sees</dt><dd id="test-name"></dd><dt>Category</dt><dd id="test-category"></dd><dt>Vibration</dt><dd id="test-vibration"></dd></dl>
    <div class="rum">${button("default", "Vibrate like a game", has("default"))}${button("left", "Left", has("left"))}${button("right", "Right", has("right"))}${button("direct", "Direct report", direct)}</div>
    <p class="res" id="test-res"></p></div></div>
    <p class="count" id="test-count"></p>
    <div class="seen" id="test-seen">${CONTROLS.map((c) => `<span data-c="${c}">${c}</span>`).join("")}</div>
    <div class="tg"><div>LT<i><i id="test-lt"></i></i></div><div>RT<i><i id="test-rt"></i></i></div></div>`;
  $("test-name").textContent = s.name;
  $("test-category").textContent = `${s.category}, with an extended gamepad`;
  $("test-vibration").textContent = vibrationText(s.localities);
  $("test-res").textContent = directLine();
  body.querySelectorAll("[data-op]").forEach((b) => (b.onclick = () => vibrate(b.dataset.op)));
  body.querySelectorAll("#test-pic [data-k]").forEach((e) => { e.dataset.off = e.getAttribute(e.tagName === "path" ? "stroke" : "fill") || ""; });
  paintSeen();
}

function paintSeen() {
  document.querySelectorAll("#test-seen [data-c]").forEach((e) => e.classList.toggle("s", testSeen.has(e.dataset.c)));
  const count = $("test-count");
  if (count) count.innerHTML = `<b>${testSeen.size} of ${CONTROLS.length}</b> controls checked. Press each one to check it.`;
}

function paintInput(e) {
  const pressed = new Set(e.pressed || []);
  document.querySelectorAll("#test-pic [data-k]").forEach((el) => {
    const k = el.dataset.k;
    if (k === "LS" || k === "RS") {
      const [x, y] = k === "LS" ? [e.lx, e.ly] : [e.rx, e.ry];
      el.setAttribute("transform", `translate(${+(x * STICK_TRAVEL).toFixed(2)} ${+(-y * STICK_TRAVEL).toFixed(2)})`);
      el.children[1].setAttribute("fill", pressed.has(k === "LS" ? "L3" : "R3") ? ACCENT : "#424851");
    } else {
      el.setAttribute(el.tagName === "path" ? "stroke" : "fill", pressed.has(k) ? ACCENT : el.dataset.off);
    }
  });
  document.querySelectorAll("#test-seen [data-c]").forEach((el) => el.classList.toggle("now", pressed.has(el.dataset.c)));
  $("test-lt").style.width = `${Math.round(e.lt * 100)}%`;
  $("test-rt").style.width = `${Math.round(e.rt * 100)}%`;
}

function vibrate(op) {
  if (testPending || !bridge()) return;
  testPending = op;
  const id = ++testId;
  document.querySelectorAll("[data-op]").forEach((b) => { b.dataset.was = b.disabled ? "1" : ""; b.disabled = true; });
  testTimer = setTimeout(() => finishVibrate("No answer from the app."), RESULT_TIMEOUT_MS);
  bridge().postMessage(op === "direct" ? { op: "direct", id } : { op: "vibrate", locality: op, id });
}

function finishVibrate(line) {
  clearTimeout(testTimer);
  testPending = null;
  document.querySelectorAll("[data-op]").forEach((b) => { b.disabled = b.dataset.was === "1"; });
  const res = $("test-res");
  if (res) res.textContent = line;
}

window.u2cDiagnostics = (e) => {
  if (!testVisible) return;
  if (e.type === "state") {
    if (e.connected && testName && e.name !== testName) testSeen = new Set();
    if (e.connected) testName = e.name;
    testState = e;
    if (testConnected !== null && testConnected !== !!e.connected && !busy) refresh();
    testConnected = !!e.connected;
    diagnosticsRender();
  } else if (e.type === "input" && testMode() === "live" && $("test-lt")) {
    for (const p of e.pressed || []) testSeen.add(p);
    if (Math.hypot(e.lx, e.ly) > STICK_SEEN) testSeen.add("LS");
    if (Math.hypot(e.rx, e.ry) > STICK_SEEN) testSeen.add("RS");
    if (e.lt > TRIGGER_SEEN) testSeen.add("LT");
    if (e.rt > TRIGGER_SEEN) testSeen.add("RT");
    paintInput(e);
    paintSeen();
  } else if (e.type === "result" && testPending && e.id === testId) {
    const direct = testPending === "direct";
    finishVibrate(!e.ok ? e.error || "It couldn't be sent." : direct ? "Sent. You'll only feel it if Rumble over Bluetooth is installed." : "Sent. Did you feel it?");
  }
};
