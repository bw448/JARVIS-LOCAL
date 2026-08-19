# JARVIS LOCAL 0.5.0

0.5.0 是一次以响应速度和语音对话自然度为中心的兼容升级。界面布局保持不变，主要重构文字生成、朗读调度、连续录音和模型启动路径。

## 主要变化

- 新增 `/api/chat/stream` 本机 NDJSON 流式接口；兼容服务不支持流式时自动回退到原 `/api/chat`。
- 回答文字渐进显示，完整短句生成后立即进入 TTS 队列，语音与后续文字生成并行。
- 每个语音队列使用独立会话编号；停止朗读或开始新录音时会取消旧的模型请求、音频请求和播放。
- 连续语音期间复用麦克风 MediaStream，退出语音模式后才释放设备。
- 设置版本升级到 5，旧版默认 1.2 秒停顿迁移为 0.8 秒。
- 本地 STT/TTS 在启动后后台预热；模型不可用时继续显示原有能力诊断和回退提示。
- STT 响应携带识别耗时，TTS 使用 `Server-Timing` 返回合成耗时，流式聊天结束事件包含首字与总耗时。
- 助手改名不再改变三个 HUD 的中心内容，中心固定使用产品声波标识。
- 对话策略增强情绪回应，同时保持任务真实性和高风险操作确认要求。

## 兼容性

- 原有 `/api/chat`、`/api/stt`、`/api/tts` 和设置字段继续可用。
- 原有 Kokoro、MeloTTS、faster-whisper、系统语音和外部 TTS 配置继续可用。
- SenseVoice、Qwen3-TTS 和 CosyVoice3 尚未伪装为内置组件；后续可通过独立本地模型包和语音工作进程接入。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check .\jarvis\static\app.js
node --check .\jarvis\static\floating.js
```
