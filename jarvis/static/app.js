"use strict";

const byId = id => document.getElementById(id);
const ui = Object.fromEntries([
  "product-name", "app-version", "assistant-name", "owner-line", "core-monogram",
  "conversation-assistant-name", "system-status", "voice-core", "voice-state-label",
  "voice-state-detail", "brain-status", "brain-indicator", "stt-status", "stt-indicator",
  "tts-status", "tts-indicator", "message-list", "message-input", "send-button",
  "microphone-button", "stop-speech-button", "recording-banner", "recording-time",
  "voice-mode-button", "voice-mode-card-button", "voice-mode-overlay", "voice-mode-end-button",
  "voice-mode-mute-button", "voice-hud-core", "voice-hud-monogram", "voice-hud-label",
  "voice-hud-detail", "voice-live-transcript", "voice-level-label", "settings-dialog",
  "settings-form", "settings-message", "toast", "speech-player", "api-key-state",
  "temperature-output", "speed-output", "silence-output", "opacity-output",
  "floating-opacity-output",
  "sherpa-tts-fields", "kokoro-tts-fields", "external-tts-field", "stt-detail-fields",
  "sensevoice-stt-field",
  "test-voice-button", "voice-test-status",
].map(id => [id, byId(id)]));

const channel = "BroadcastChannel" in window
  ? new BroadcastChannel("jarvis-local-ui")
  : null;

const state = {
  bootstrap: null,
  messages: [],
  busy: false,
  voiceState: "idle",
  voiceMode: false,
  voiceModeStarting: false,
  voiceResumeTimer: null,
  recorder: null,
  recordingStream: null,
  recordingChunks: [],
  recordingStartedAt: 0,
  recordingTimer: null,
  recordingMimeType: "",
  recordingPurpose: "manual",
  recordingDiscard: false,
  recordingHasSpeech: false,
  recordingCycle: 0,
  voiceCaptureStream: null,
  voiceStatusCheckedAt: 0,
  audioContext: null,
  analyser: null,
  analyserData: null,
  analyserFrame: null,
  noiseFloor: 0.008,
  speechCandidateAt: 0,
  lastVoiceAt: 0,
  toastTimer: null,
  errorResetTimer: null,
  audioUrl: null,
  speechController: null,
  speechSession: 0,
  speechQueue: [],
  speechQueueClosed: true,
  speechQueueRunning: false,
  speechQueueWake: null,
  speechPlaybackResolve: null,
  chatController: null,
  chatSession: 0,
};

const voiceCopy = {
  idle: ["待命", "可以输入文字，或开启连续语音"],
  listening: ["正在聆听", "请直接说话，说完稍作停顿"],
  transcribing: ["正在识别", "声音只交给本机识别引擎"],
  thinking: ["正在思考", "文字模型正在生成回答"],
  speaking: ["正在回应", "本机正在生成并播放声音"],
  error: ["需要处理", "请检查提示后重试"],
};

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `请求失败（HTTP ${response.status}）`);
  return payload;
}

function showToast(message, isError = false) {
  clearTimeout(state.toastTimer);
  ui.toast.textContent = message;
  ui.toast.classList.toggle("error", isError);
  ui.toast.classList.add("visible");
  state.toastTimer = setTimeout(() => ui.toast.classList.remove("visible"), 3600);
}

function broadcastState() {
  if (!state.bootstrap) return;
  const payload = {
    type: "state",
    voiceState: state.voiceState,
    voiceMode: state.voiceMode,
    assistantName: state.bootstrap.settings.identity.assistant_name,
    theme: state.bootstrap.settings.appearance?.theme || "cyan",
    floatingOpacity: Number(state.bootstrap.settings.appearance?.floating_opacity ?? 0.85),
  };
  channel?.postMessage(payload);
  void callDesktop(
    "update_floating_status",
    payload.voiceState,
    payload.voiceMode,
    payload.assistantName,
    payload.theme,
    payload.floatingOpacity,
  );
}

function updateVoiceModeControls() {
  const active = state.voiceMode;
  document.body.dataset.voiceMode = String(active);
  ui["voice-mode-button"].setAttribute("aria-pressed", String(active));
  ui["voice-mode-card-button"].setAttribute("aria-pressed", String(active));
  ui["voice-mode-card-button"].querySelector("strong").textContent = active
    ? "连续语音运行中"
    : "开启连续语音";
  ui["voice-mode-card-button"].querySelector("small").textContent = active
    ? "直接说话；回答结束后会继续聆听"
    : "说完自动识别、发送并等待下一句话";
  ui["voice-mode-overlay"].hidden = !active;
}

function setVoiceState(next, detail = "") {
  const copy = voiceCopy[next] || voiceCopy.idle;
  state.voiceState = next;
  document.body.dataset.voiceState = next;
  ui["voice-core"].dataset.state = next;
  ui["voice-hud-core"].dataset.state = next;
  ui["voice-state-label"].textContent = copy[0];
  ui["voice-state-detail"].textContent = detail || copy[1];
  ui["voice-hud-label"].textContent = copy[0];
  ui["voice-hud-detail"].textContent = detail || copy[1];
  const listening = next === "listening";
  ui["microphone-button"].setAttribute("aria-pressed", String(listening));
  ui["microphone-button"].querySelector("span").textContent = listening
    ? state.voiceMode ? "连续聆听" : "结束录音"
    : "单次说话";
  ui["stop-speech-button"].disabled = next !== "speaking";
  broadcastState();
}

function reportVoiceError(error, resumeDelay = 0) {
  const message = error instanceof Error ? error.message : String(error);
  clearTimeout(state.errorResetTimer);
  setVoiceState("error", message);
  showToast(message, true);
  state.errorResetTimer = setTimeout(() => {
    if (state.voiceState === "error") setVoiceState("idle");
    if (state.voiceMode) scheduleVoiceResume(resumeDelay || 500);
  }, 3600);
}

function setIndicator(element, status) {
  element.className = `module-indicator ${status}`;
}

function displayProviderHost(baseUrl) {
  try {
    return new URL(baseUrl).host;
  } catch {
    return "未配置";
  }
}

function ttsProviderLabel(provider) {
  return {
    sherpa_kokoro: "Kokoro 本地女声",
    sherpa_onnx: "MeloTTS 本地语音",
    kokoro: "Kokoro Python",
    system: "Windows 系统语音",
    external: "本地高品质语音服务",
  }[provider] || provider;
}

function ttsNotReadyLabel(capability) {
  return {
    sherpa_package_missing: "缺少本地语音运行库",
    sherpa_model_missing: "缺少本地声音模型",
    kokoro_package_missing: "缺少 Kokoro",
    external_url_missing: "未填写服务地址",
    worker_unreachable: "本地语音工作进程未就绪",
  }[capability.reason] || "尚未就绪";
}

function applyAppearance(settings) {
  const appearance = settings.appearance || {};
  const theme = appearance.theme || "cyan";
  const opacity = Number(appearance.panel_opacity ?? 0.68);
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.setProperty(
    "--panel-opacity",
    String(Math.max(0.30, Math.min(0.96, opacity))),
  );
  void callDesktop("set_main_opacity", opacity);
  broadcastState();
}

function renderSystemState() {
  const { app, settings, capabilities, secrets } = state.bootstrap;
  const assistant = settings.identity.assistant_name;
  const owner = settings.identity.owner_name;
  document.title = `${assistant} · ${app.name}`;
  ui["product-name"].textContent = app.name;
  ui["app-version"].textContent = app.version;
  ui["assistant-name"].textContent = ""; ui["assistant-name"].style.display = "none";
  ui["conversation-assistant-name"].textContent = ""; ui["conversation-assistant-name"].style.display = "none";
  ui["owner-line"].textContent = `为${owner}服务`;
  // Identity belongs to conversation, not to the product's visual core.
  // Renaming the assistant must never turn the HUD into a large initial.
  applyAppearance(settings);

  const brainReady = settings.brain.provider !== "disabled";
  ui["brain-status"].textContent = brainReady
    ? `${settings.brain.model} · ${displayProviderHost(settings.brain.base_url)}`
    : "尚未接入文字模型";
  setIndicator(ui["brain-indicator"], brainReady ? "ready" : "warning");

  const sttEnabled = settings.stt.provider !== "disabled";
  const sttReady = sttEnabled && capabilities.stt.ready;
  ui["stt-status"].textContent = !sttEnabled
    ? "已关闭"
    : sttReady
      ? settings.stt.provider === "sensevoice"
        ? `SenseVoice · ${displayProviderHost(settings.stt.external_url)}`
        : `本机 Whisper ${settings.stt.model}`
      : "本地识别尚未就绪";
  setIndicator(ui["stt-indicator"], !sttEnabled || sttReady ? "ready" : "warning");

  const tts = capabilities.tts;
  const preset = tts.voice_presets?.find(item => item.speaker_id === settings.tts.speaker_id);
  ui["tts-status"].textContent = tts.ready
    ? preset?.label || ttsProviderLabel(settings.tts.provider)
    : settings.tts.browser_fallback ? `${ttsNotReadyLabel(tts)} · 可回退` : ttsNotReadyLabel(tts);
  setIndicator(ui["tts-indicator"], tts.ready ? "ready" : "warning");

  const voiceUsable = tts.ready || settings.tts.browser_fallback;
  const allReady = brainReady && (!sttEnabled || sttReady) && voiceUsable;
  ui["system-status"].dataset.state = allReady ? "ready" : "warning";
  ui["system-status"].querySelector(".status-copy").textContent = allReady
    ? "系统待命"
    : "有项目待配置";
  ui["api-key-state"].textContent = secrets.brain_api_key_saved
    ? "Windows 凭据库中已有密钥"
    : "当前未保存密钥";
  broadcastState();
}

function appendMessage(role, content, options = {}) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}${options.error ? " error" : ""}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  const assistant = state.bootstrap?.settings.identity.assistant_name || "JARVIS";
  const owner = state.bootstrap?.settings.identity.owner_name || "YOU";
  avatar.innerHTML = role === "user"
    ? '<svg viewBox="0 0 24 24" width="18" height="18"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" fill="currentColor"/></svg>'
    : '<svg viewBox="0 0 24 24" width="18" height="18"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="currentColor"/></svg>';

  const contentWrap = document.createElement("div");
  contentWrap.className = "message-content";
  const meta = document.createElement("p");
  meta.className = "message-meta";
  meta.textContent = role === "user" ? owner : assistant;
  const bubble = document.createElement("p");
  bubble.className = "message-bubble";
  if (options.thinking) {
    const dots = document.createElement("span");
    dots.className = "thinking-dots";
    for (let index = 0; index < 3; index += 1) dots.appendChild(document.createElement("i"));
    bubble.appendChild(dots);
  } else {
    bubble.textContent = content;
  }
  contentWrap.append(meta, bubble);
  wrapper.append(avatar, contentWrap);
  ui["message-list"].appendChild(wrapper);
  ui["message-list"].scrollTop = ui["message-list"].scrollHeight;
  return wrapper;
}

function prepareStreamingMessage(wrapper) {
  const bubble = wrapper.querySelector(".message-bubble");
  bubble.replaceChildren();
  bubble.textContent = "";
  wrapper.dataset.streaming = "true";
  return bubble;
}

function updateStreamingMessage(wrapper, text) {
  const bubble = wrapper.querySelector(".message-bubble");
  bubble.textContent = text;
  ui["message-list"].scrollTop = ui["message-list"].scrollHeight;
}

function addWelcomeMessage() {
  const { assistant_name: assistant, owner_name: owner } = state.bootstrap.settings.identity;
  const voiceReady = state.bootstrap.capabilities.tts.ready && state.bootstrap.capabilities.stt.ready;
  appendMessage(
    "assistant",
    `${owner}，我是 ${assistant}。${voiceReady ? "离线听说功能已经就绪。" : "部分语音组件需要检查。"}\n\n直接输入任务，或开启左侧“连续语音”，说完后无需再点击发送。`,
  );
}

function resizeComposer() {
  const textarea = ui["message-input"];
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 150)}px`;
}

function clearVoiceResumeTimer() {
  clearTimeout(state.voiceResumeTimer);
  state.voiceResumeTimer = null;
}

function scheduleVoiceResume(delay = 450) {
  clearVoiceResumeTimer();
  if (!state.voiceMode) return;
  state.voiceResumeTimer = setTimeout(() => {
    state.voiceResumeTimer = null;
    if (
      state.voiceMode
      && !state.busy
      && !state.recorder
      && !["speaking", "thinking", "transcribing"].includes(state.voiceState)
    ) {
      void startRecording({ automatic: true });
    }
  }, delay);
}

async function readChatStream(messages, controller, onEvent, voiceContext = null) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    signal: controller.signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, voice_context: voiceContext }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `请求失败（HTTP ${response.status}）`);
  }
  if (!response.body?.getReader) throw new Error("当前窗口不支持流式回答");

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffered = "";
  let doneEvent = null;
  const consumeLine = rawLine => {
    const line = rawLine.trim();
    if (!line) return;
    const event = JSON.parse(line);
    if (event.type === "error") throw new Error(event.error || "模型流生成失败");
    if (event.type === "done") doneEvent = event;
    onEvent(event);
  };

  while (true) {
    const { value, done } = await reader.read();
    buffered += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffered.split("\n");
    buffered = lines.pop() || "";
    for (const line of lines) consumeLine(line);
    if (done) break;
  }
  if (buffered.trim()) consumeLine(buffered);
  if (!doneEvent) throw new Error("模型流意外结束");
  return doneEvent;
}

function speechSafeText(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, " 代码内容已显示在屏幕上。")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/https?:\/\/\S+/g, "链接已显示在屏幕上")
    .replace(/[>*#_~|]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractSpeechSegments(buffer, flush = false) {
  const segments = [];
  let rest = buffer;
  while (rest.length) {
    let boundary = -1;
    for (let index = 0; index < rest.length; index += 1) {
      const char = rest[index];
      if ("。！？!?；;\n".includes(char) && index >= 5) {
        boundary = index + 1;
        break;
      }
      if ("，,：:".includes(char) && index >= 34) {
        boundary = index + 1;
        break;
      }
      if (index >= 72) {
        boundary = index + 1;
        break;
      }
    }
    if (boundary < 0) break;
    const segment = speechSafeText(rest.slice(0, boundary));
    if (segment) segments.push(segment);
    rest = rest.slice(boundary);
  }
  if (flush) {
    const segment = speechSafeText(rest);
    if (segment) segments.push(segment);
    rest = "";
  }
  return { segments, rest };
}

async function sendMessage(providedText = "", options = {}) {
  if (state.busy) {
    if (!options.voice) showToast("上一条任务仍在处理中");
    return false;
  }
  const text = (providedText || ui["message-input"].value).trim();
  if (!text) return false;

  const chatSession = state.chatSession + 1;
  state.chatSession = chatSession;
  state.busy = true;
  clearVoiceResumeTimer();
  pauseVoiceCapture(true);
  stopSpeech(false);
  ui["send-button"].disabled = true;
  ui["message-input"].value = "";
  resizeComposer();
  state.messages.push({ role: "user", content: text });
  appendMessage("user", text);
  const responseMessage = appendMessage("assistant", "", { thinking: true });
  let responseBubble = null;
  let answer = "";
  let speechBuffer = "";
  let toolProposal = null;
  const settings = state.bootstrap.settings;
  const shouldSpeak = state.voiceMode || settings.tts.auto_speak;
  const speechSession = shouldSpeak ? beginSpeechStream() : null;
  const controller = new AbortController();
  state.chatController = controller;
  setVoiceState("thinking", "正在生成回答，首句会立即回应");

  const acceptDelta = delta => {
    if (!delta) return;
    if (!responseBubble) responseBubble = prepareStreamingMessage(responseMessage);
    answer += delta;
    updateStreamingMessage(responseMessage, answer);
    if (speechSession !== null) {
      speechBuffer += delta;
      const extracted = extractSpeechSegments(speechBuffer);
      speechBuffer = extracted.rest;
      for (const segment of extracted.segments) enqueueSpeech(segment, speechSession);
    }
  };

  const acceptSilentText = textValue => {
    if (!textValue) return;
    if (!responseBubble) responseBubble = prepareStreamingMessage(responseMessage);
    answer += textValue;
    updateStreamingMessage(responseMessage, answer);
  };

  try {
    let metrics = null;
    if (settings.interaction?.streaming_responses !== false) {
      const done = await readChatStream(
        state.messages.slice(-24),
        controller,
        event => {
          if (event.type === "delta") acceptDelta(String(event.text || ""));
          if (event.type === "tool_result") {
            acceptDelta(`\n\n${String(event.message || "操作已经完成")}`);
          }
          if (event.type === "tool_proposal" && event.proposal) {
            toolProposal = event.proposal;
            const risk = event.proposal.risk === "high" ? "高影响操作" : "低风险操作";
            acceptSilentText(
              `\n\n操作预览（${risk}）：${String(event.proposal.preview || "未提供说明")}`,
            );
          }
        },
        options.voiceContext || null,
      );
      metrics = done.metrics || null;
      if (!answer.trim() && done.answer) acceptDelta(String(done.answer));
    } else {
      const payload = await fetchJSON("/api/chat", {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: state.messages.slice(-24),
          voice_context: options.voiceContext || null,
        }),
      });
      acceptDelta(String(payload.answer || ""));
    }

    if (toolProposal) {
      setVoiceState("thinking", "等待你确认电脑操作");
      const approved = window.confirm(
        `${toolProposal.title || "电脑操作"}\n\n${toolProposal.preview}\n\n是否允许执行？`,
      );
      const result = await fetchJSON("/api/tools/resolve", {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proposal_id: toolProposal.proposal_id,
          approved,
        }),
      });
      acceptDelta(`\n\n${String(result.message || (approved ? "操作已经完成。" : "操作已取消。"))}`);
    }

    answer = answer.trim();
    if (!answer) throw new Error("文字模型没有返回内容");
    responseMessage.dataset.streaming = "false";
    state.messages.push({ role: "assistant", content: answer });

    if (speechSession !== null) {
      const extracted = extractSpeechSegments(speechBuffer, true);
      for (const segment of extracted.segments) enqueueSpeech(segment, speechSession);
      closeSpeechStream(speechSession);
    } else if (settings.interaction?.proactive_speech) {
      void speak(`${settings.identity.owner_name}，任务已经完成，请查看结果。`);
    } else {
      setVoiceState("idle");
    }
    if (settings.privacy?.diagnostic_logging && metrics) {
      console.info("[JARVIS timing]", metrics);
    }
    return true;
  } catch (error) {
    if (speechSession !== null) stopSpeech(false);
    if (error.name === "AbortError") {
      if (!answer) responseMessage.remove();
      else responseMessage.dataset.streaming = "false";
      setVoiceState("idle", "当前回答已停止");
      return false;
    }
    if (!answer) responseMessage.remove();
    else responseMessage.dataset.streaming = "false";
    appendMessage("assistant", error.message, { error: true });
    reportVoiceError(error, 700);
    return false;
  } finally {
    if (state.chatController === controller) state.chatController = null;
    if (state.chatSession === chatSession) {
      state.busy = false;
      ui["send-button"].disabled = false;
      if (!state.voiceMode) ui["message-input"].focus();
    }
  }
}

function releaseAudioUrl() {
  if (!state.audioUrl) return;
  URL.revokeObjectURL(state.audioUrl);
  state.audioUrl = null;
}

function stopSpeech(setIdle = true) {
  state.speechSession += 1;
  state.speechQueue = [];
  state.speechQueueClosed = true;
  state.speechQueueRunning = false;
  if (state.speechQueueWake) state.speechQueueWake();
  state.speechQueueWake = null;
  if (state.speechController) {
    state.speechController.abort();
    state.speechController = null;
  }
  if (state.speechPlaybackResolve) state.speechPlaybackResolve(false);
  state.speechPlaybackResolve = null;
  ui["speech-player"].pause();
  ui["speech-player"].removeAttribute("src");
  ui["speech-player"].load();
  releaseAudioUrl();
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  if (setIdle && state.voiceState === "speaking") setVoiceState("idle");
}

function completeSpeechSession(session) {
  if (session !== state.speechSession) return;
  releaseAudioUrl();
  setVoiceState("idle", state.voiceMode ? "回答完成，正在重新打开麦克风" : "回答完成");
  if (state.voiceMode) scheduleVoiceResume(420);
}

function beginSpeechStream() {
  clearVoiceResumeTimer();
  pauseVoiceCapture(true);
  stopSpeech(false);
  const session = state.speechSession;
  state.speechQueue = [];
  state.speechQueueClosed = false;
  state.speechQueueRunning = false;
  return session;
}

function enqueueSpeech(text, session, options = {}) {
  if (session !== state.speechSession || state.speechQueueClosed) return false;
  if (!options.isTest && !String(text || "").trim()) return false;
  state.speechQueue.push({ text, ...options });
  if (state.speechQueueWake) state.speechQueueWake();
  state.speechQueueWake = null;
  if (!state.speechQueueRunning) void drainSpeechQueue(session);
  return true;
}

function closeSpeechStream(session) {
  if (session !== state.speechSession) return;
  state.speechQueueClosed = true;
  if (state.speechQueueWake) state.speechQueueWake();
  state.speechQueueWake = null;
  if (!state.speechQueueRunning) void drainSpeechQueue(session);
}

function browserSpeakSegment(text, session, speed) {
  return new Promise((resolve, reject) => {
    if (!("speechSynthesis" in window)) {
      reject(new Error("当前系统不支持系统语音朗读"));
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    utterance.rate = speed;
    const voices = window.speechSynthesis.getVoices();
    utterance.voice = voices.find(voice => voice.lang.toLowerCase().startsWith("zh")) || null;
    const cancelPlayback = () => resolve(false);
    state.speechPlaybackResolve = cancelPlayback;
    utterance.onstart = () => {
      if (session === state.speechSession) setVoiceState("speaking", "正在使用系统语音朗读");
    };
    utterance.onend = () => resolve(true);
    utterance.onerror = event => {
      if (["canceled", "interrupted"].includes(event.error)) resolve(false);
      else reject(new Error(`系统语音朗读失败：${event.error || "未知错误"}`));
    };
    window.speechSynthesis.speak(utterance);
  }).finally(() => {
    if (session === state.speechSession) state.speechPlaybackResolve = null;
  });
}

function playCurrentAudio(session) {
  let ended;
  let failed;
  return new Promise((resolve, reject) => {
    state.speechPlaybackResolve = resolve;
    ended = () => resolve(true);
    failed = () => reject(new Error("本地音频播放失败"));
    ui["speech-player"].addEventListener("ended", ended, { once: true });
    ui["speech-player"].addEventListener("error", failed, { once: true });
    ui["speech-player"].play().catch(reject);
  }).finally(() => {
    ui["speech-player"].removeEventListener("ended", ended);
    ui["speech-player"].removeEventListener("error", failed);
    if (session === state.speechSession) state.speechPlaybackResolve = null;
  });
}

async function playSpeechSegment(job, session) {
  const controller = new AbortController();
  state.speechController = controller;
  setVoiceState("speaking", job.isTest ? "正在生成试听声音" : "正在生成下一句声音");

  try {
    const requestOptions = {
      method: "POST",
      signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      body: job.isTest
        ? JSON.stringify({ settings: job.previewSettings || state.bootstrap.settings })
        : JSON.stringify({ text: job.text }),
    };
    const response = await fetch(job.isTest ? "/api/voice/test" : "/api/tts", requestOptions);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "语音合成失败");
    }
    if (session !== state.speechSession) return false;

    const contentType = response.headers.get("Content-Type") || "";
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      if (payload.mode !== "browser" || !payload.text) throw new Error("语音服务返回了无效结果");
      const speed = job.previewSettings?.tts?.speed || state.bootstrap.settings.tts.speed;
      return await browserSpeakSegment(payload.text, session, speed);
    }

    const blob = await response.blob();
    if (!blob.size) throw new Error("语音服务没有返回音频");
    state.audioUrl = URL.createObjectURL(blob);
    ui["speech-player"].src = state.audioUrl;
    ui["speech-player"].dataset.session = String(session);
    const activeSettings = job.previewSettings || state.bootstrap.settings;
    if (session === state.speechSession) {
      setVoiceState("speaking", `正在播放${ttsProviderLabel(activeSettings.tts.provider)}`);
    }
    await playCurrentAudio(session);
    releaseAudioUrl();
    return true;
  } catch (error) {
    if (error.name === "AbortError") return false;
    if (session === state.speechSession) reportVoiceError(error, 700);
    return false;
  } finally {
    if (state.speechController === controller) state.speechController = null;
  }
}

async function drainSpeechQueue(session) {
  if (session !== state.speechSession || state.speechQueueRunning) return;
  state.speechQueueRunning = true;
  try {
    while (session === state.speechSession) {
      const job = state.speechQueue.shift();
      if (job) {
        const played = await playSpeechSegment(job, session);
        if (!played && session === state.speechSession) {
          stopSpeech(false);
          break;
        }
        continue;
      }
      if (state.speechQueueClosed) break;
      await new Promise(resolve => {
        state.speechQueueWake = resolve;
      });
    }
    if (session === state.speechSession && state.speechQueueClosed && !state.speechQueue.length) {
      completeSpeechSession(session);
    }
  } finally {
    if (session === state.speechSession) state.speechQueueRunning = false;
  }
}

async function speak(text = "", isTest = false, previewSettings = null) {
  const session = beginSpeechStream();
  if (isTest) {
    enqueueSpeech("", session, { isTest: true, previewSettings });
  } else {
    const extracted = extractSpeechSegments(String(text || ""), true);
    for (const segment of extracted.segments) enqueueSpeech(segment, session);
  }
  closeSpeechStream(session);
  return true;
}

function cleanupVoiceAnalysis() {
  if (state.analyserFrame) cancelAnimationFrame(state.analyserFrame);
  state.analyserFrame = null;
  state.analyser = null;
  state.analyserData = null;
  if (state.audioContext) void state.audioContext.close().catch(() => {});
  state.audioContext = null;
  document.documentElement.style.setProperty("--voice-level", ".18");
  ui["voice-level-label"].textContent = "INPUT 00%";
}

function releaseVoiceCaptureStream() {
  if (!state.voiceCaptureStream) return;
  for (const track of state.voiceCaptureStream.getTracks()) track.stop();
  state.voiceCaptureStream = null;
}

function cleanupRecordingStream({ releaseDevice = false } = {}) {
  cleanupVoiceAnalysis();
  if (state.recordingStream && state.recordingStream !== state.voiceCaptureStream) {
    for (const track of state.recordingStream.getTracks()) track.stop();
  }
  state.recordingStream = null;
  if (releaseDevice) releaseVoiceCaptureStream();
  clearInterval(state.recordingTimer);
  state.recordingTimer = null;
  ui["recording-banner"].hidden = true;
  ui["microphone-button"].disabled = false;
}

function updateRecordingClock() {
  const elapsed = Math.floor((Date.now() - state.recordingStartedAt) / 1000);
  const minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const seconds = String(elapsed % 60).padStart(2, "0");
  ui["recording-time"].textContent = `${minutes}:${seconds}`;
  const maximum = state.bootstrap.settings.stt.recording_seconds || 45;
  if (elapsed >= maximum) stopRecording({ discard: !state.recordingHasSpeech });
}

function chooseRecordingMimeType() {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  return candidates.find(type => MediaRecorder.isTypeSupported(type)) || "";
}

function setupVoiceActivityDetector(stream, cycle) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) throw new Error("当前窗口不支持自动停顿检测");
  const context = new AudioContextClass();
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.35;
  context.createMediaStreamSource(stream).connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);
  state.audioContext = context;
  state.analyser = analyser;
  state.analyserData = samples;
  state.noiseFloor = 0.008;
  state.speechCandidateAt = 0;
  state.lastVoiceAt = 0;

  const analyze = () => {
    if (
      !state.voiceMode
      || cycle !== state.recordingCycle
      || state.recorder?.state !== "recording"
      || state.analyser !== analyser
    ) return;

    analyser.getByteTimeDomainData(samples);
    let energy = 0;
    for (const sample of samples) {
      const normalized = (sample - 128) / 128;
      energy += normalized * normalized;
    }
    const rms = Math.sqrt(energy / samples.length);
    const visualLevel = Math.max(.08, Math.min(1, rms * 11));
    document.documentElement.style.setProperty("--voice-level", visualLevel.toFixed(3));
    ui["voice-level-label"].textContent = `INPUT ${String(Math.round(visualLevel * 100)).padStart(2, "0")}%`;

    const now = performance.now();
    const threshold = Math.max(0.024, Math.min(0.09, state.noiseFloor * 3.2));
    if (rms > threshold) {
      if (!state.speechCandidateAt) state.speechCandidateAt = now;
      if (now - state.speechCandidateAt >= 110) {
        state.recordingHasSpeech = true;
        state.lastVoiceAt = now;
        setVoiceState("listening", "已经听到你说话，停顿后会自动发送");
      }
    } else {
      if (!state.recordingHasSpeech) {
        state.noiseFloor = Math.max(0.004, state.noiseFloor * 0.94 + rms * 0.06);
      }
      state.speechCandidateAt = 0;
      const silenceSeconds = Number(state.bootstrap.settings.interaction?.silence_seconds || 0.8);
      if (
        state.recordingHasSpeech
        && state.lastVoiceAt
        && now - state.lastVoiceAt >= silenceSeconds * 1000
        && Date.now() - state.recordingStartedAt >= 650
      ) {
        stopRecording();
        return;
      }
    }
    state.analyserFrame = requestAnimationFrame(analyze);
  };
  state.analyserFrame = requestAnimationFrame(analyze);
}

async function refreshVoiceStatus() {
  try {
    const payload = await fetchJSON("/api/voice/status");
    state.bootstrap.capabilities = payload.capabilities;
    state.bootstrap.runtime = payload.runtime || state.bootstrap.runtime;
    state.voiceStatusCheckedAt = Date.now();
    renderSystemState();
  } catch {
    // Keep the last known state if refresh races with desktop shutdown.
  }
}

function validateRecordingSupport() {
  const settings = state.bootstrap.settings.stt;
  if (settings.provider === "disabled") throw new Error("语音识别已在设置中关闭");
  if (!state.bootstrap.capabilities.stt.ready) throw new Error("本地 Whisper 尚未就绪");
  if (!navigator.mediaDevices?.getUserMedia || !("MediaRecorder" in window)) {
    throw new Error("当前桌面窗口不支持麦克风录音");
  }
}

async function startRecording({ automatic = false } = {}) {
  if (state.recorder || state.voiceModeStarting) return false;
  state.voiceModeStarting = automatic;
  try {
    if (!state.voiceStatusCheckedAt || Date.now() - state.voiceStatusCheckedAt > 30_000) {
      await refreshVoiceStatus();
    }
    validateRecordingSupport();
    if (!automatic) stopSpeech(false);

    let stream = automatic ? state.voiceCaptureStream : null;
    const reusable = stream?.getAudioTracks().some(track => track.readyState === "live");
    if (!reusable) {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      if (automatic) state.voiceCaptureStream = stream;
    }
    if (automatic && !state.voiceMode) {
      for (const track of stream.getTracks()) track.stop();
      if (state.voiceCaptureStream === stream) state.voiceCaptureStream = null;
      return false;
    }

    state.recordingStream = stream;
    state.recordingMimeType = chooseRecordingMimeType();
    const options = state.recordingMimeType ? { mimeType: state.recordingMimeType } : undefined;
    const recorder = new MediaRecorder(stream, options);
    state.recordingMimeType = recorder.mimeType || state.recordingMimeType || "audio/webm";
    state.recordingChunks = [];
    state.recordingPurpose = automatic ? "voice" : "manual";
    state.recordingDiscard = false;
    state.recordingHasSpeech = !automatic;
    state.recordingCycle += 1;
    const cycle = state.recordingCycle;
    state.recorder = recorder;
    recorder.ondataavailable = event => {
      if (event.data.size) state.recordingChunks.push(event.data);
    };
    recorder.onerror = () => reportVoiceError(new Error("麦克风录音失败"), 700);
    recorder.onstop = () => void finishRecording(state.recordingPurpose, state.recordingDiscard, cycle);
    recorder.start(250);
    state.recordingStartedAt = Date.now();
    ui["recording-time"].textContent = "00:00";
    ui["recording-banner"].hidden = false;
    setVoiceState(
      "listening",
      automatic ? "直接说话；系统会在停顿后自动发送" : "再次点击即可结束录音",
    );
    state.recordingTimer = setInterval(updateRecordingClock, 500);
    if (automatic) setupVoiceActivityDetector(stream, cycle);
    return true;
  } catch (error) {
    cleanupRecordingStream({ releaseDevice: automatic });
    if (automatic) {
      state.voiceMode = false;
      updateVoiceModeControls();
    }
    reportVoiceError(new Error(`无法使用麦克风：${error.message || error}`));
    return false;
  } finally {
    state.voiceModeStarting = false;
  }
}

function stopRecording({ discard = false } = {}) {
  if (state.recorder?.state !== "recording") return;
  state.recordingDiscard = discard;
  cleanupVoiceAnalysis();
  ui["microphone-button"].disabled = true;
  state.recorder.stop();
  if (!discard) setVoiceState("transcribing", "正在整理这句话");
}

function pauseVoiceCapture(discard = true) {
  clearVoiceResumeTimer();
  if (state.recorder?.state === "recording") stopRecording({ discard });
}

async function finishRecording(purpose, discard, cycle) {
  const chunks = state.recordingChunks;
  state.recordingChunks = [];
  const mediaType = state.recordingMimeType || chunks[0]?.type || "audio/webm";
  state.recorder = null;
  cleanupRecordingStream();

  if (discard || !chunks.length) {
    if (state.voiceMode && cycle === state.recordingCycle && !state.busy) {
      setVoiceState("idle", "没有检测到说话，继续等待");
      scheduleVoiceResume(260);
    }
    return;
  }

  const blob = new Blob(chunks, { type: mediaType });
  if (!blob.size) {
    reportVoiceError(new Error("没有采集到录音，请检查麦克风权限"), 600);
    return;
  }

  setVoiceState("transcribing");
  ui["microphone-button"].disabled = true;
  try {
    const response = await fetch("/api/stt", {
      method: "POST",
      headers: { "Content-Type": mediaType },
      body: blob,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "语音识别失败");
    const transcript = String(payload.text || "").trim();
    if (!transcript) throw new Error("没有识别到清晰语音");
    ui["voice-live-transcript"].textContent = transcript;

    if (state.voiceMode && purpose === "voice") {
      setVoiceState("idle", "已识别，正在发送");
      await sendMessage(transcript, {
        voice: true,
        voiceContext: { emotion: payload.emotion || "", language: payload.language || "" },
      });
    } else if (state.bootstrap.settings.stt.auto_send_transcript) {
      setVoiceState("idle");
      await sendMessage(transcript, {
        voice: true,
        voiceContext: { emotion: payload.emotion || "", language: payload.language || "" },
      });
    } else {
      ui["message-input"].value = transcript;
      resizeComposer();
      ui["message-input"].focus();
      setVoiceState("idle", "识别结果已放入输入框，请确认后发送");
      showToast("语音已转成文字，请确认后发送");
    }
  } catch (error) {
    reportVoiceError(error, 700);
  } finally {
    ui["microphone-button"].disabled = false;
    if (
      state.voiceMode
      && !state.busy
      && !["speaking", "thinking", "transcribing"].includes(state.voiceState)
    ) scheduleVoiceResume(500);
  }
}

async function toggleRecording() {
  if (state.chatController || state.voiceState === "speaking") {
    if (state.chatController) state.chatController.abort();
    stopSpeech(false);
    setVoiceState("idle", "已停止当前回答，正在打开麦克风");
    await Promise.resolve();
  }
  if (state.voiceMode) await setVoiceMode(false);
  if (state.recorder?.state === "recording") {
    stopRecording();
    return;
  }
  await startRecording({ automatic: false });
}

async function setVoiceMode(enabled) {
  const next = Boolean(enabled);
  if (next === state.voiceMode || state.voiceModeStarting) return state.voiceMode;
  clearVoiceResumeTimer();

  if (!next) {
    state.voiceMode = false;
    pauseVoiceCapture(true);
    releaseVoiceCaptureStream();
    updateVoiceModeControls();
    if (["listening", "transcribing"].includes(state.voiceState)) setVoiceState("idle");
    broadcastState();
    return false;
  }

  state.voiceMode = true;
  state.voiceStatusCheckedAt = 0;
  updateVoiceModeControls();
  ui["voice-live-transcript"].textContent = "等待你的声音…";
  broadcastState();
  const started = await startRecording({ automatic: true });
  if (!started) {
    state.voiceMode = false;
    updateVoiceModeControls();
    broadcastState();
  }
  return state.voiceMode;
}

function refreshConditionalFields() {
  const ttsProvider = byId("setting-tts-provider").value;
  const sherpaProvider = ["sherpa_kokoro", "sherpa_onnx"].includes(ttsProvider);
  ui["sherpa-tts-fields"].hidden = !sherpaProvider;
  byId("sherpa-vits-speaker-field").hidden = ttsProvider !== "sherpa_onnx";
  ui["kokoro-tts-fields"].hidden = ttsProvider !== "kokoro";
  ui["external-tts-field"].hidden = ttsProvider !== "external";
  byId("tts-model-hint").textContent = ttsProvider === "sherpa_kokoro"
    ? "完整离线版会自动使用包内 Kokoro 模型，无需填写目录。"
    : "兼容旧版 MeloTTS；默认说话人编号为 0。";
  const sttProvider = byId("setting-stt-provider").value;
  const sttDisabled = sttProvider === "disabled";
  ui["sensevoice-stt-field"].hidden = sttProvider !== "sensevoice";
  ui["stt-detail-fields"].classList.toggle("disabled-fields", sttDisabled);
  for (const control of ui["stt-detail-fields"].querySelectorAll("input, select")) {
    control.disabled = sttDisabled;
  }
  byId("setting-stt-device").disabled = sttDisabled || sttProvider === "sensevoice";
}

function selectTtsProviderDefaults() {
  const provider = byId("setting-tts-provider").value;
  if (provider === "external") {
    const voice = byId("setting-external-voice");
    if (!voice.value.trim() || voice.value.trim().startsWith("zf_")) voice.value = "Vivian";
    const endpoint = byId("setting-tts-url");
    if (!endpoint.value.trim()) endpoint.value = "http://127.0.0.1:9880/v1/audio/speech";
  }
  refreshConditionalFields();
}

function selectSttProviderDefaults() {
  const provider = byId("setting-stt-provider").value;
  const model = byId("setting-stt-model");
  const whisperModels = ["tiny", "base", "small", "medium"];
  if (provider === "sensevoice" && whisperModels.includes(model.value)) {
    model.value = "SenseVoiceSmall";
    if (!byId("setting-stt-url").value.trim()) {
      byId("setting-stt-url").value = "http://127.0.0.1:50000/v1/audio/transcriptions";
    }
  } else if (provider === "faster_whisper" && model.value === "SenseVoiceSmall") {
    model.value = "small";
  }
  refreshConditionalFields();
}

function setSelectValue(select, value) {
  const exists = Array.from(select.options).some(option => option.value === value);
  if (!exists && value) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = `${value}（自定义）`;
    select.appendChild(option);
  }
  select.value = value;
}

function setVoicePresetValue(settings) {
  const select = byId("setting-kokoro-voice-preset");
  const value = String(settings.tts.provider === "sherpa_kokoro" ? settings.tts.speaker_id : 47);
  let option = Array.from(select.options).find(item => item.value === value);
  if (!option) {
    option = document.createElement("option");
    option.value = value;
    option.dataset.voice = settings.tts.voice;
    option.textContent = `${settings.tts.voice} · 自定义音色 ${value}`;
    select.appendChild(option);
  }
  select.value = value;
}

function creativityLabel(value) {
  const number = Number(value);
  if (number <= 0.35) return `严谨 · ${number.toFixed(1)}`;
  if (number <= 0.85) return `平衡 · ${number.toFixed(1)}`;
  return `自由 · ${number.toFixed(1)}`;
}

function fillSettingsForm() {
  const { settings, secrets } = state.bootstrap;
  const appearance = settings.appearance || { theme: "cyan", panel_opacity: 0.68, floating_opacity: 0.85, floating_window: true };
  const interaction = settings.interaction || { voice_mode_auto_start: false, proactive_speech: true, silence_seconds: 0.8, streaming_responses: true, prewarm_models: true, computer_control_enabled: false };
  byId("setting-assistant-name").value = settings.identity.assistant_name;
  byId("setting-owner-name").value = settings.identity.owner_name;
  byId("setting-personality").value = settings.identity.personality;
  byId("setting-brain-provider").value = settings.brain.provider;
  byId("setting-brain-model").value = settings.brain.model;
  byId("setting-brain-url").value = settings.brain.base_url;
  byId("setting-brain-timeout").value = settings.brain.timeout_seconds;
  byId("setting-temperature").value = Math.min(1.2, settings.brain.temperature);
  ui["temperature-output"].textContent = creativityLabel(byId("setting-temperature").value);
  byId("setting-api-key").value = "";
  byId("setting-clear-api-key").checked = false;
  ui["api-key-state"].textContent = secrets.brain_api_key_saved
    ? "Windows 凭据库中已有密钥"
    : "当前未保存密钥";

  byId("setting-tts-provider").value = settings.tts.provider;
  byId("setting-tts-speed").value = settings.tts.speed;
  ui["speed-output"].textContent = Number(settings.tts.speed).toFixed(2).replace(/0$/, "");
  byId("setting-tts-model-dir").value = settings.tts.model_dir;
  byId("setting-tts-speaker-id").value = settings.tts.provider === "sherpa_onnx" ? settings.tts.speaker_id : 0;
  setVoicePresetValue(settings);
  byId("setting-tts-threads").value = settings.tts.num_threads;
  byId("setting-tts-voice").value = settings.tts.voice;
  byId("setting-external-voice").value = settings.tts.voice;
  byId("setting-tts-url").value = settings.tts.external_url;
  byId("setting-tts-instructions").value = settings.tts.instructions || "";
  byId("setting-auto-speak").checked = settings.tts.auto_speak;
  byId("setting-browser-fallback").checked = settings.tts.browser_fallback;

  byId("setting-stt-provider").value = settings.stt.provider;
  setSelectValue(byId("setting-stt-model"), settings.stt.model);
  byId("setting-stt-device").value = settings.stt.device;
  byId("setting-stt-language").value = settings.stt.language;
  byId("setting-stt-url").value = settings.stt.external_url || "";
  byId("setting-recording-seconds").value = settings.stt.recording_seconds;
  byId("setting-auto-send-transcript").checked = settings.stt.auto_send_transcript;

  byId("setting-voice-mode-auto-start").checked = interaction.voice_mode_auto_start;
  byId("setting-proactive-speech").checked = interaction.proactive_speech;
  byId("setting-computer-control").checked = interaction.computer_control_enabled;
  byId("setting-silence-seconds").value = interaction.silence_seconds;
  ui["silence-output"].textContent = `${Number(interaction.silence_seconds).toFixed(1)} 秒`;
  byId("setting-theme").value = appearance.theme;
  byId("setting-panel-opacity").value = appearance.panel_opacity;
  ui["opacity-output"].textContent = `${Math.round(Number(appearance.panel_opacity) * 100)}%`;
  byId("setting-floating-opacity").value = appearance.floating_opacity ?? 0.85;
  ui["floating-opacity-output"].textContent = `${Math.round(Number(appearance.floating_opacity ?? 0.85) * 100)}%`;
  byId("setting-floating-window").checked = appearance.floating_window;

  ui["settings-message"].textContent = "";
  ui["voice-test-status"].textContent = "语音完全在本机生成";
  refreshConditionalFields();
}

async function openSettings() {
  if (state.voiceMode) await setVoiceMode(false);
  await refreshVoiceStatus();
  fillSettingsForm();
  if (!ui["settings-dialog"].open) ui["settings-dialog"].showModal();
}

function closeSettings(restoreAppearance = true) {
  if (restoreAppearance && state.bootstrap) applyAppearance(state.bootstrap.settings);
  if (ui["settings-dialog"].open) ui["settings-dialog"].close();
}

function numberValue(id, fallback) {
  const parsed = Number(byId(id).value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function collectSettings() {
  const current = state.bootstrap.settings;
  const ttsProvider = byId("setting-tts-provider").value;
  const presetOption = byId("setting-kokoro-voice-preset").selectedOptions[0];
  const selectedVoice = ttsProvider === "sherpa_kokoro"
    ? presetOption?.dataset.voice || current.tts.voice
    : ttsProvider === "external"
      ? byId("setting-external-voice").value.trim()
      : ttsProvider === "kokoro"
        ? byId("setting-tts-voice").value.trim()
        : current.tts.voice;
  const selectedSpeakerId = ttsProvider === "sherpa_kokoro"
    ? Number(presetOption?.value ?? 47)
    : numberValue("setting-tts-speaker-id", current.tts.speaker_id);

  return {
    version: 7,
    identity: {
      assistant_name: byId("setting-assistant-name").value.trim(),
      owner_name: byId("setting-owner-name").value.trim(),
      personality: byId("setting-personality").value.trim(),
    },
    brain: {
      provider: byId("setting-brain-provider").value,
      base_url: byId("setting-brain-url").value.trim() || current.brain.base_url,
      model: byId("setting-brain-model").value.trim() || current.brain.model,
      temperature: numberValue("setting-temperature", current.brain.temperature),
      timeout_seconds: numberValue("setting-brain-timeout", current.brain.timeout_seconds),
    },
    tts: {
      provider: ttsProvider,
      voice: selectedVoice || current.tts.voice || "default",
      speed: numberValue("setting-tts-speed", current.tts.speed),
      model_dir: byId("setting-tts-model-dir").value.trim(),
      speaker_id: selectedSpeakerId,
      num_threads: numberValue("setting-tts-threads", current.tts.num_threads),
      external_url: byId("setting-tts-url").value.trim(),
      instructions: byId("setting-tts-instructions").value.trim(),
      browser_fallback: byId("setting-browser-fallback").checked,
      auto_speak: byId("setting-auto-speak").checked,
    },
    stt: {
      provider: byId("setting-stt-provider").value,
      model: byId("setting-stt-model").value,
      device: byId("setting-stt-device").value,
      language: byId("setting-stt-language").value.trim() || "zh",
      external_url: byId("setting-stt-url").value.trim(),
      auto_send_transcript: byId("setting-auto-send-transcript").checked,
      recording_seconds: numberValue("setting-recording-seconds", current.stt.recording_seconds),
    },
    appearance: {
      theme: byId("setting-theme").value,
      panel_opacity: numberValue("setting-panel-opacity", current.appearance?.panel_opacity || 0.68),
      floating_opacity: numberValue("setting-floating-opacity", current.appearance?.floating_opacity || 0.85),
      floating_window: byId("setting-floating-window").checked,
    },
    interaction: {
      voice_mode_auto_start: byId("setting-voice-mode-auto-start").checked,
      proactive_speech: byId("setting-proactive-speech").checked,
      silence_seconds: numberValue("setting-silence-seconds", current.interaction?.silence_seconds || 0.8),
      streaming_responses: current.interaction?.streaming_responses !== false,
      prewarm_models: current.interaction?.prewarm_models !== false,
      computer_control_enabled: byId("setting-computer-control").checked,
    },
    privacy: current.privacy,
  };
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

async function saveSettings(event) {
  event.preventDefault();
  const settings = collectSettings();
  const apiKey = byId("setting-api-key").value.trim();
  const clearKey = byId("setting-clear-api-key").checked;
  const payload = {
    settings,
    api_key_action: clearKey ? "clear" : apiKey ? "set" : "keep",
    api_key: apiKey,
  };

  byId("save-settings-button").disabled = true;
  ui["settings-message"].textContent = "正在保存…";
  try {
    state.bootstrap = await fetchJSON("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderSystemState();
    fillSettingsForm();
    closeSettings(false);
    await callDesktop("set_floating_enabled", settings.appearance.floating_window);
    showToast("设置已保存并应用");
  } catch (error) {
    ui["settings-message"].textContent = error.message;
  } finally {
    byId("save-settings-button").disabled = false;
  }
}

async function testVoice() {
  ui["test-voice-button"].disabled = true;
  const settings = collectSettings();
  const selectedVoice = byId("setting-kokoro-voice-preset").selectedOptions[0];
  const voiceLabel = settings.tts.provider === "sherpa_kokoro"
    ? selectedVoice?.textContent || settings.tts.voice
    : ttsProviderLabel(settings.tts.provider);
  ui["voice-test-status"].textContent = `正在生成：${voiceLabel}`;
  const played = await speak("", true, settings);
  ui["voice-test-status"].textContent = played
    ? `正在试听：${voiceLabel}`
    : "试听失败，请查看状态提示";
  ui["test-voice-button"].disabled = false;
}

function clearChat() {
  if (state.messages.length && !window.confirm("清空当前内存中的会话内容？此操作无法撤销。")) return;
  stopSpeech();
  pauseVoiceCapture(true);
  state.messages = [];
  ui["message-list"].replaceChildren();
  addWelcomeMessage();
  if (state.voiceMode) scheduleVoiceResume(450);
  showToast("当前会话已清空");
}

function previewAppearance() {
  const theme = byId("setting-theme").value;
  const opacity = numberValue("setting-panel-opacity", 0.68);
  const floatingOpacity = numberValue("setting-floating-opacity", 0.85);
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.setProperty("--panel-opacity", String(opacity));
  ui["opacity-output"].textContent = `${Math.round(opacity * 100)}%`;
  ui["floating-opacity-output"].textContent = `${Math.round(floatingOpacity * 100)}%`;
  void callDesktop("set_main_opacity", opacity);
  void callDesktop("preview_floating_appearance", theme, floatingOpacity);
}

function bindEvents() {
  byId("open-settings-button").addEventListener("click", () => void openSettings());
  byId("close-settings-button").addEventListener("click", () => closeSettings());
  byId("cancel-settings-button").addEventListener("click", () => closeSettings());
  byId("clear-chat-button").addEventListener("click", clearChat);
  ui["settings-form"].addEventListener("submit", saveSettings);
  ui["send-button"].addEventListener("click", () => void sendMessage());
  ui["microphone-button"].addEventListener("click", () => void toggleRecording());
  ui["stop-speech-button"].addEventListener("click", () => {
    stopSpeech();
    if (state.voiceMode) scheduleVoiceResume(350);
  });
  ui["voice-mode-button"].addEventListener("click", () => void setVoiceMode(!state.voiceMode));
  ui["voice-mode-card-button"].addEventListener("click", () => void setVoiceMode(!state.voiceMode));
  ui["voice-mode-end-button"].addEventListener("click", () => void setVoiceMode(false));
  ui["voice-mode-mute-button"].addEventListener("click", () => {
    if (state.chatController) state.chatController.abort();
    stopSpeech();
    if (state.voiceMode) scheduleVoiceResume(350);
  });
  ui["test-voice-button"].addEventListener("click", () => void testVoice());
  byId("setting-tts-provider").addEventListener("change", selectTtsProviderDefaults);
  byId("setting-stt-provider").addEventListener("change", selectSttProviderDefaults);
  byId("setting-temperature").addEventListener("input", event => {
    ui["temperature-output"].textContent = creativityLabel(event.target.value);
  });
  byId("setting-tts-speed").addEventListener("input", event => {
    ui["speed-output"].textContent = Number(event.target.value).toFixed(2).replace(/0$/, "");
  });
  byId("setting-silence-seconds").addEventListener("input", event => {
    ui["silence-output"].textContent = `${Number(event.target.value).toFixed(1)} 秒`;
  });
  byId("setting-theme").addEventListener("change", previewAppearance);
  byId("setting-panel-opacity").addEventListener("input", previewAppearance);
  byId("setting-floating-opacity").addEventListener("input", previewAppearance);
  ui["message-input"].addEventListener("input", resizeComposer);
  ui["message-input"].addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      void sendMessage();
    }
  });
  ui["settings-dialog"].addEventListener("click", event => {
    if (event.target === ui["settings-dialog"]) closeSettings();
  });
  ui["settings-dialog"].addEventListener("cancel", event => {
    event.preventDefault();
    closeSettings();
  });
  channel?.addEventListener("message", event => {
    const message = event.data || {};
    if (message.type === "toggle-voice-mode") void setVoiceMode(!state.voiceMode);
    if (message.type === "request-state") broadcastState();
  });
  window.addEventListener("beforeunload", () => {
    state.voiceMode = false;
    clearVoiceResumeTimer();
    if (state.recorder?.state === "recording") stopRecording({ discard: true });
    cleanupRecordingStream({ releaseDevice: true });
    if (state.chatController) state.chatController.abort();
    stopSpeech(false);
    channel?.close();
  });
}

window.jarvisDesktop = {
  toggleVoiceMode: () => setVoiceMode(!state.voiceMode),
  setVoiceMode: enabled => setVoiceMode(Boolean(enabled)),
  openSettings,
};

async function initialize() {
  bindEvents();
  updateVoiceModeControls();
  setVoiceState("idle");
  try {
    state.bootstrap = await fetchJSON("/api/bootstrap");
    renderSystemState();
    fillSettingsForm();
    addWelcomeMessage();
    ui["message-input"].focus();
    if (state.bootstrap.settings.interaction?.voice_mode_auto_start) {
      setTimeout(() => void setVoiceMode(true), 650);
    }
  } catch (error) {
    ui["system-status"].dataset.state = "warning";
    ui["system-status"].querySelector(".status-copy").textContent = "本地服务未连接";
    reportVoiceError(error);
  }
}

void initialize();

// 强制清除所有可能显示助手名字的元素
(function() {
  function cleanMonograms() {
    // 清除所有 monogram 元素的文字
    document.querySelectorAll('.hud-monogram, .signal-monogram, .hud-name, #float-monogram').forEach(el => {
      if (el.textContent && el.textContent.trim()) {
        el.textContent = '';
      }
    });
    // 确保 assistant-name 不显示
    const assistantEl = document.getElementById('assistant-name');
    if (assistantEl) {
      assistantEl.style.display = 'none';
      assistantEl.textContent = '';
    }
    // 确保 conversation-assistant-name 不显示
    const convEl = document.getElementById('conversation-assistant-name');
    if (convEl) {
      convEl.style.display = 'none';
      convEl.textContent = '';
    }
  }
  // 立即执行
  cleanMonograms();
  // 每 500ms 检查一次
  setInterval(cleanMonograms, 500);
})();

// 强制清除语音模式中央的所有文字
(function() {
  function cleanVoiceMonogram() {
    var el = document.getElementById('voice-hud-monogram');
    if (el) {
      // 保留 img 子元素，清除其他所有文字
      var img = el.querySelector('img');
      el.innerHTML = '';
      if (img) {
        el.appendChild(img);
      }
      // 设置样式确保没有文字
      el.style.color = 'transparent';
      el.style.fontSize = '0';
    }
  }
  // 立即执行
  cleanVoiceMonogram();
  // 每 100ms 检查一次
  setInterval(cleanVoiceMonogram, 100);
})();
