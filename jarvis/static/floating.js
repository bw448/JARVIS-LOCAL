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
  monogram.textContent = Array.from(payload.assistantName || "JARVIS")
    .slice(0, 10)
    .join("")
    .toUpperCase();
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
