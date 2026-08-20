"use strict";

const byId = id => document.getElementById(id);
const action = byId("float-action");
const shell = byId("widget-shell");
const emblem = byId("hud-emblem");
const dragHandle = byId("widget-drag-handle");
const edgeRail = byId("edge-rail");
const monogram = byId("float-monogram");
const statusLabel = byId("float-status-label");
const modeLabel = byId("float-mode-label");
const channel = "BroadcastChannel" in window
  ? new BroadcastChannel("jarvis-local-ui")
  : null;

const labels = {
  idle: "系统待命",
  listening: "正在聆听",
  transcribing: "本地识别",
  thinking: "正在思考",
  speaking: "正在回应",
  error: "需要处理",
};

let voiceMode = false;
let collapseTimer = null;
const autoCollapseEnabled = new URLSearchParams(window.location.search)
  .get("autocollapse") !== "0";

function drawHudEmblem() {
  if (!(emblem instanceof HTMLCanvasElement)) return;
  const context = emblem.getContext("2d");
  if (!context) return;
  const artwork = new Image();
  artwork.decoding = "async";
  artwork.addEventListener("load", () => {
    context.clearRect(0, 0, emblem.width, emblem.height);
    context.drawImage(artwork, 0, 0, emblem.width, emblem.height);
  }, { once: true });
  artwork.src = "/static/jarvis-hud-logo.png";
}

function clearCollapseTimer() {
  clearTimeout(collapseTimer);
  collapseTimer = null;
}

async function callDesktop(method, ...args) {
  const api = window.pywebview?.api;
  if (!api || typeof api[method] !== "function") return false;
  try {
    return await api[method](...args);
  } catch {
    return false;
  }
}

function applyState(payload = {}) {
  const voiceState = payload.voiceState || "idle";
  voiceMode = Boolean(payload.voiceMode);
  document.body.dataset.state = voiceState;
  document.body.dataset.voiceMode = String(voiceMode);
  document.body.dataset.theme = payload.theme || "cyan";
  document.documentElement.style.setProperty(
    "--floating-opacity",
    String(Math.max(0.25, Math.min(1, Number(payload.floatingOpacity ?? 0.85)))),
  );
  action.setAttribute("aria-pressed", String(voiceMode));
  action.setAttribute("aria-label", voiceMode ? "关闭连续语音模式" : "开启连续语音模式");
  statusLabel.textContent = labels[voiceState] || labels.idle;
  modeLabel.textContent = voiceMode ? "连续语音运行中" : "点击核心开始对话";
}

function applyHostState(payload = {}) {
  const edge = payload.edge === "left" ? "left" : "right";
  const collapsed = Boolean(payload.collapsed);
  document.body.dataset.edge = edge;
  document.body.dataset.collapsed = String(collapsed);
  document.body.dataset.active = String(Boolean(payload.active));
  edgeRail.setAttribute("aria-label", collapsed ? "展开悬浮助手" : "悬浮助手已展开");
}

window.jarvisFloating = { applyHostState };

async function expandWidget() {
  clearCollapseTimer();
  await callDesktop("expand_floating");
}

function scheduleCollapse(delay = 420) {
  if (!autoCollapseEnabled) return;
  clearCollapseTimer();
  collapseTimer = setTimeout(() => {
    collapseTimer = null;
    void callDesktop("collapse_floating");
  }, delay);
}

async function activateWidget(active) {
  await callDesktop("set_floating_active", Boolean(active));
}

channel?.addEventListener("message", event => {
  const message = event.data || {};
  if (message.type === "state") applyState(message);
});

action.addEventListener("click", async event => {
  event.stopPropagation();
  await activateWidget(true);
  const handled = await callDesktop("toggle_voice_mode");
  if (!handled) channel?.postMessage({ type: "toggle-voice-mode" });
  scheduleCollapse(900);
});

byId("float-expand").addEventListener("click", async event => {
  event.stopPropagation();
  clearCollapseTimer();
  await activateWidget(true);
  const handled = await callDesktop("show_main");
  if (!handled) channel?.postMessage({ type: "show-main" });
});

byId("float-hide").addEventListener("click", async event => {
  event.stopPropagation();
  clearCollapseTimer();
  const handled = await callDesktop("hide_floating");
  if (!handled) document.body.hidden = true;
});

edgeRail.addEventListener("pointerenter", () => void expandWidget());
edgeRail.addEventListener("focus", () => void expandWidget());
edgeRail.addEventListener("click", async event => {
  event.stopPropagation();
  await activateWidget(true);
  await expandWidget();
});

shell.addEventListener("pointerenter", () => void expandWidget());
shell.addEventListener("pointerleave", () => scheduleCollapse());
shell.addEventListener("pointerdown", () => {
  clearCollapseTimer();
  void activateWidget(true);
});
shell.addEventListener("pointerup", event => {
  if (event.pointerType === "touch") scheduleCollapse(1300);
});

dragHandle.addEventListener("pointerdown", clearCollapseTimer);
dragHandle.addEventListener("pointerup", () => void callDesktop("dock_floating"));

window.addEventListener("focus", () => void activateWidget(true));
window.addEventListener("blur", () => {
  void activateWidget(false);
  scheduleCollapse(260);
});

document.addEventListener("contextmenu", event => event.preventDefault());
window.addEventListener("beforeunload", () => {
  clearCollapseTimer();
  channel?.close();
});

void (async () => {
  drawHudEmblem();
  const hostState = await callDesktop("get_floating_state");
  if (hostState && typeof hostState === "object") applyHostState(hostState);
  channel?.postMessage({ type: "request-state" });
})();

// 强制清除所有可能显示助手名字的元素
(function() {
  function cleanMonograms() {
    document.querySelectorAll('.hud-name, #float-monogram').forEach(el => {
      // 保留 img 子元素，清除其他文字
      const img = el.querySelector('img');
      if (img) {
        el.textContent = '';
        el.appendChild(img);
      }
    });
  }
  cleanMonograms();
  setInterval(cleanMonograms, 500);
})();

// Voice Waveform Visualization
class VoiceWaveform {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.width = this.canvas.width;
    this.height = this.canvas.height;
    this.bars = 24;
    this.barWidth = this.width / this.bars - 2;
    this.animationId = null;
    this.isActive = false;
    this.frequencies = new Array(this.bars).fill(0);
    this.targetFrequencies = new Array(this.bars).fill(0);
    this.phase = 0;
  }

  start() {
    if (this.isActive) return;
    this.isActive = true;
    this.animate();
  }

  stop() {
    this.isActive = false;
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
    this.clear();
  }

  clear() {
    if (!this.ctx) return;
    this.ctx.clearRect(0, 0, this.width, this.height);
  }

  generateFrequencies() {
    this.phase += 0.05;
    for (let i = 0; i < this.bars; i++) {
      const base = Math.sin(this.phase + i * 0.3) * 0.3 + 0.5;
      const noise = Math.random() * 0.4;
      this.targetFrequencies[i] = Math.min(1, base + noise);
    }
  }

  animate() {
    if (!this.isActive) return;

    this.generateFrequencies();

    // Smooth interpolation
    for (let i = 0; i < this.bars; i++) {
      this.frequencies[i] += (this.targetFrequencies[i] - this.frequencies[i]) * 0.15;
    }

    this.draw();
    this.animationId = requestAnimationFrame(() => this.animate());
  }

  draw() {
    if (!this.ctx) return;

    this.ctx.clearRect(0, 0, this.width, this.height);

    const style = getComputedStyle(document.documentElement);
    const hudColor = style.getPropertyValue("--hud").trim() || "#54f4ee";
    const hudRgb = style.getPropertyValue("--hud-rgb").trim() || "84, 244, 238";

    for (let i = 0; i < this.bars; i++) {
      const x = i * (this.barWidth + 2) + 1;
      const barHeight = this.frequencies[i] * this.height * 0.8;
      const y = (this.height - barHeight) / 2;

      const gradient = this.ctx.createLinearGradient(x, y, x, y + barHeight);
      gradient.addColorStop(0, `rgba(${hudRgb}, 0.9)`);
      gradient.addColorStop(0.5, `rgba(${hudRgb}, 0.7)`);
      gradient.addColorStop(1, `rgba(${hudRgb}, 0.5)`);

      this.ctx.fillStyle = gradient;
      this.ctx.beginPath();
      this.ctx.roundRect(x, y, this.barWidth, barHeight, 2);
      this.ctx.fill();

      // Glow effect
      this.ctx.shadowColor = hudColor;
      this.ctx.shadowBlur = 4;
      this.ctx.fill();
      this.ctx.shadowBlur = 0;
    }
  }
}

// Initialize voice waveform
const voiceWaveform = new VoiceWaveform("voice-waveform");

// Update applyState to control waveform
const originalApplyState = applyState;
applyState = function(payload = {}) {
  originalApplyState(payload);
  
  const voiceState = payload.voiceState || "idle";
  if (voiceState === "listening" || voiceState === "speaking") {
    voiceWaveform.start();
  } else {
    voiceWaveform.stop();
  }
};

// Theme Switcher
document.querySelectorAll('.theme-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const theme = btn.dataset.theme;
    document.body.dataset.theme = theme;
    localStorage.setItem('jarvis-theme', theme);
    channel?.postMessage({ type: 'theme-change', theme });
  });
});

// Load saved theme
const savedTheme = localStorage.getItem('jarvis-theme');
if (savedTheme) {
  document.body.dataset.theme = savedTheme;
}
