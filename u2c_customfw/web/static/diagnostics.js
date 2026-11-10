// SPDX-License-Identifier: GPL-3.0-or-later
// The controller test: shows what macOS's GameController reports, through the Mac app's native bridge
// (macos/Diagnostics.swift). It sends the bridge {op} messages and receives window.u2cDiagnostics(event).
const CONTROLS = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "L3", "R3", "View", "Menu", "Home", "Up", "Down", "Left", "Right", "LS", "RS"];  // as Diagnostics.swift names them
const CONTROL_LABELS = { L3: "Left stick press", R3: "Right stick press", View: "− (Select)", Menu: "+ (Start)", Up: "D-pad up", Down: "D-pad down", Left: "D-pad left", Right: "D-pad right", LS: "Left stick", RS: "Right stick" };  // as printed on the controller
const STICK_SEEN = 0.5, TRIGGER_SEEN = 0.1, STICK_TRAVEL = 7, RESULT_TIMEOUT_MS = 3000, ACCENT = "#3fc8b4";
const IDLE_LINE = "Vibrates for under a second. Nothing is written to the controller.";

let testVisible = false, testConnected = null, testState = null, testSeen = new Set(), testName = null, testMounted = null, testPending = null, testTimer = null, testId = 0;
const bridge = () => window.u2cSimBridge || (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.diagnostics);  // the simulator's, then the Mac app's

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
  mountCirc();
}

const directAvailable = () => !!st && st.devices.some((d) => d.mode === "bluetooth_xbox");

const directLine = () => directAvailable() ? IDLE_LINE
  : st && st.devices.some((d) => d.mode === "bluetooth") ? "The direct report needs the Xbox Series X|S controller tweak."
  : "The direct report only works over Bluetooth.";

function batteryText(b) {  // macOS defaults to level 0 and an unknown state when it has nothing to report
  if (!b || b.level < 0 || (b.state === "unknown" && b.level === 0)) return "macOS doesn't report the battery for this controller";
  if (b.state === "full") return "Full";
  return `${Math.round(b.level * 100)} %${b.state === "charging" ? ", charging" : ""}`;
}

function paintBattery() {
  const row = $("test-battery");
  if (row && testState) row.textContent = batteryText(testState.battery);
}

function vibrationText(localities) {
  if (!localities.length) return "Not available";
  return localities.includes("left") && localities.includes("right") ? "Available, also on the left and right sides separately" : "Available";
}

function mountLive(body) {
  const s = testState, has = (l) => s.localities.includes(l), direct = directAvailable();
  const button = (op, label, ok) => `<button class="sec small" data-op="${op}" data-was="${ok ? "" : "1"}"${ok && !testPending ? "" : " disabled"}>${label}</button>`;
  body.innerHTML = `<div class="test"><div class="test-pic" id="test-pic">${pad(ACCENT, false, "test-g")}</div><div>
    <dl class="rows"><dt>macOS sees</dt><dd id="test-name"></dd><dt>Category</dt><dd id="test-category"></dd><dt>Vibration</dt><dd id="test-vibration"></dd><dt>Battery</dt><dd id="test-battery"></dd></dl>
    <div class="rum">${button("default", "Vibrate Like a Game", has("default"))}${button("left", "Left Motor", has("left"))}${button("right", "Right Motor", has("right"))}${button("direct", "Direct Report", direct)}</div>
    <p class="res" id="test-res"></p></div></div>
    <p class="count" id="test-count"></p>
    <div class="seen" id="test-seen">${CONTROLS.map((c) => `<span data-c="${c}">${CONTROL_LABELS[c] || c}</span>`).join("")}</div>
    <div class="tg"><div>LT<i><i id="test-lt"></i></i></div><div>RT<i><i id="test-rt"></i></i></div></div>`;
  $("test-name").textContent = s.name;
  $("test-category").textContent = `${s.category}, with an extended gamepad`;
  $("test-vibration").textContent = vibrationText(s.localities);
  $("test-res").textContent = directLine();
  paintBattery();
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
  updateCirc(e.lx, e.ly, e.rx, e.ry);
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
  if (e.type === "result" && e.op === "ring") {  // the Home ring card is in another tab
    if (ringAsked && e.id === ringAsked.id) ringDone(e.ok ? null : e.error || "It couldn't be sent.", ringAsked.level, ringAsked.save);
    return;
  }
  if (e.type === "input" && tab === "settings") return settingsLive(e);
  if (!testVisible) return;
  if (e.type === "state") {
    if (e.connected && testName && e.name !== testName) testSeen = new Set();
    if (e.connected) testName = e.name;
    testState = e;
    if (testConnected !== null && testConnected !== !!e.connected && !busy) refresh();
    testConnected = !!e.connected;
    diagnosticsRender();
    paintBattery();
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

let circMounted = false, circL = null, circR = null;

class StickTester {
  constructor(canvasId, lxId, lyId, errId, secId) {
    this.canvas = $(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.lxEl = $(lxId);
    this.lyEl = $(lyId);
    this.errEl = $(errId);
    this.secEl = $(secId);
    this.numBins = 32;
    this.maxR = new Float32Array(this.numBins);
    this.currX = 0;
    this.currY = 0;

    const dpr = window.devicePixelRatio || 1;
    this.size = 200;
    this.canvas.width = this.size * dpr;
    this.canvas.height = this.size * dpr;
    this.canvas.style.width = `${this.size}px`;
    this.canvas.style.height = `${this.size}px`;
    this.ctx.scale(dpr, dpr);
    this.draw();
  }

  reset() {
    this.maxR.fill(0);
    this.currX = 0;
    this.currY = 0;
    if (this.lxEl) this.lxEl.textContent = "+0.00000";
    if (this.lyEl) this.lyEl.textContent = "+0.00000";
    if (this.errEl) {
      this.errEl.textContent = "Avg Error: 0.0%";
      this.errEl.style.color = "var(--dim)";
    }
    if (this.secEl) this.secEl.textContent = "0 / 32 sectors";
    this.draw();
  }

  update(x, y) {
    this.currX = x;
    this.currY = y;
    if (this.lxEl) this.lxEl.textContent = (x >= 0 ? "+" : "") + x.toFixed(5);
    if (this.lyEl) this.lyEl.textContent = (y >= 0 ? "+" : "") + y.toFixed(5);

    const r = Math.hypot(x, y);
    if (r > 0.4) {
      let angle = Math.atan2(y, x);
      if (angle < 0) angle += 2 * Math.PI;
      const bin = Math.floor((angle / (2 * Math.PI)) * this.numBins) % this.numBins;
      if (r > this.maxR[bin]) {
        this.maxR[bin] = Math.min(r, 1.8);
      }
    }

    let sum = 0, count = 0;
    for (let i = 0; i < this.numBins; i++) {
      if (this.maxR[i] > 0) {
        count++;
        sum += Math.abs(this.maxR[i] - 1.0);
      }
    }

    if (this.errEl) {
      if (count > 0) {
        const avg = (sum / count) * 100;
        this.errEl.textContent = `Avg Error: ${avg.toFixed(1)}%`;
        this.errEl.style.color = avg > 12 ? "var(--warn)" : "var(--accent)";
      } else {
        this.errEl.textContent = "Avg Error: 0.0%";
        this.errEl.style.color = "var(--dim)";
      }
    }
    if (this.secEl) this.secEl.textContent = `${count} / ${this.numBins} sectors`;

    this.draw();
  }

  draw() {
    if (!this.ctx) return;
    const ctx = this.ctx, w = this.size, h = this.size, cx = w / 2, cy = h / 2, R0 = 64;
    ctx.clearRect(0, 0, w, h);

    // Subtle background circle
    ctx.beginPath();
    ctx.arc(cx, cy, R0, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 255, 255, 0.02)";
    ctx.fill();

    // Petals / wedges
    const step = (Math.PI * 2) / this.numBins;
    for (let i = 0; i < this.numBins; i++) {
      const rVal = this.maxR[i];
      if (rVal <= 0) continue;
      const a1 = -(i + 1) * step;
      const a2 = -i * step;
      const rInner = Math.min(rVal, 1.0) * R0;

      // Inner part (<= 1.0) in soft blue
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, rInner, a1, a2);
      ctx.closePath();
      ctx.fillStyle = i % 2 === 0 ? "rgba(90, 140, 245, 0.45)" : "rgba(80, 120, 230, 0.35)";
      ctx.fill();

      // Overshoot (> 1.0) in soft coral
      if (rVal > 1.0) {
        const rOuter = rVal * R0;
        ctx.beginPath();
        ctx.arc(cx, cy, rInner, a2, a1, true);
        ctx.arc(cx, cy, rOuter, a1, a2, false);
        ctx.closePath();
        ctx.fillStyle = i % 2 === 0 ? "rgba(240, 110, 110, 0.65)" : "rgba(220, 95, 95, 0.55)";
        ctx.fill();
      }
    }

    // Radial grid
    ctx.beginPath();
    for (let i = 0; i < this.numBins; i++) {
      const angle = i * step;
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(angle) * (R0 * 1.3), cy - Math.sin(angle) * (R0 * 1.3));
    }
    ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Target unit circle (r = 1.0)
    ctx.beginPath();
    ctx.arc(cx, cy, R0, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.32)";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Inner deadzone ring
    ctx.beginPath();
    ctx.arc(cx, cy, R0 * 0.14, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.1)";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Center rest dot
    ctx.beginPath();
    ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
    ctx.fill();

    // Current stick position indicator
    const px = cx + this.currX * R0;
    const py = cy - this.currY * R0;

    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(px, py);
    ctx.strokeStyle = "rgba(63, 200, 180, 0.7)";
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(px, py, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#3fc8b4";
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
}

function mountCirc() {
  const box = $("circ-body");
  if (!box) return;
  if (!circMounted) {
    box.innerHTML = `
      <div class="circ-actions">
        <div class="circ-note">Rotate each stick 2–3 times in full circles against the outer gate to measure circularity error.</div>
        <div class="btns">
          <button id="circ-reset" class="sec small">Reset Test</button>
          <button id="circ-guide-btn" class="sec small">Hardware Calibration Guide</button>
        </div>
      </div>
      <div id="circ-guide" class="circ-guide-box" hidden>
        <h4>8BitDo Ultimate 2C Hardware Calibration</h4>
        <ol>
          <li>Connect the controller by cable and leave the analog sticks centered.</li>
          <li>Hold <b>− (Select) + + (Start) + LB + RB</b> together for <b>7 seconds</b> until the status LED flashes rapidly.</li>
          <li>Slowly rotate both sticks along their full outer boundary 2–3 times, and press both triggers (<b>LT</b> and <b>RT</b>) all the way in.</li>
          <li>Press <b>− + + + LB + RB</b> once more to save calibration. The LED will stop flashing.</li>
        </ol>
      </div>
      <div class="circ-grid">
        <div class="circ-box">
          <div class="circ-info">
            <div class="circ-title">L STICK</div>
            <div class="circ-axis">Axis 0 (X)</div>
            <div class="circ-val" id="circ-lx">+0.00000</div>
            <div class="circ-axis">Axis 1 (Y)</div>
            <div class="circ-val" id="circ-ly">+0.00000</div>
          </div>
          <div class="circ-canvas-wrap">
            <canvas id="circ-cvs-l"></canvas>
            <div class="circ-error" id="circ-err-l">Avg Error: 0.0%</div>
            <div class="circ-sectors" id="circ-sec-l">0 / 32 sectors</div>
          </div>
        </div>
        <div class="circ-box">
          <div class="circ-info">
            <div class="circ-title">R STICK</div>
            <div class="circ-axis">Axis 2 (X)</div>
            <div class="circ-val" id="circ-rx">+0.00000</div>
            <div class="circ-axis">Axis 3 (Y)</div>
            <div class="circ-val" id="circ-ry">+0.00000</div>
          </div>
          <div class="circ-canvas-wrap">
            <canvas id="circ-cvs-r"></canvas>
            <div class="circ-error" id="circ-err-r">Avg Error: 0.0%</div>
            <div class="circ-sectors" id="circ-sec-r">0 / 32 sectors</div>
          </div>
        </div>
      </div>
    `;

    $("circ-reset").onclick = () => {
      if (circL) circL.reset();
      if (circR) circR.reset();
    };
    $("circ-guide-btn").onclick = () => {
      const g = $("circ-guide");
      if (g) g.hidden = !g.hidden;
    };

    circL = new StickTester("circ-cvs-l", "circ-lx", "circ-ly", "circ-err-l", "circ-sec-l");
    circR = new StickTester("circ-cvs-r", "circ-rx", "circ-ry", "circ-err-r", "circ-sec-r");
    circMounted = true;
  }
}

function updateCirc(lx, ly, rx, ry) {
  if (!circMounted) mountCirc();
  if (circL) circL.update(lx, ly);
  if (circR) circR.update(rx, ry);
}
