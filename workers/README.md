# JARVIS 离线语音工作进程

这一目录提供与主程序隔离的参考工作进程。主程序和语音模型只通过 `127.0.0.1` HTTP 通信，因此 Qwen3-TTS、CosyVoice、SenseVoice 可以各自使用不同 Python/CUDA 环境，也可以单独打包成可选模型组件。

## 统一协议

- `GET /health`：返回 `{"status":"ready","engine":"...","model":"..."}`。
- `POST /v1/audio/speech`：接受 OpenAI-compatible JSON，直接返回 `audio/wav`。
- `POST /v1/audio/transcriptions`：接受 OpenAI-compatible multipart 表单，返回至少包含 `text` 的 JSON；SenseVoice 可额外返回 `language` 和 `emotion`。
- 工作进程必须只监听 `127.0.0.1`、`localhost` 或 `::1`。

## Qwen3-TTS 0.6B

按照 Qwen3-TTS 官方说明创建独立 Python 3.12 环境，安装 `qwen-tts`、适合本机 CUDA 的 PyTorch 和 `soundfile`。准备本地 `Qwen3-TTS-12Hz-0.6B-CustomVoice` 权重后运行：

```powershell
python .\workers\qwen3_tts_server.py --model D:\Models\Qwen3-TTS-12Hz-0.6B-CustomVoice --device cuda:0 --port 9880
```

在 JARVIS 设置中选择“本地高品质服务 / 兼容 TTS”，接口填写：

```text
http://127.0.0.1:9880/v1/audio/speech
```

内置中文音色可填写 `Vivian` 或 `Serena`。“语音风格指令”会作为官方 `instruct` 参数传入，用于控制自然度和情绪风格。参考工作进程面向 CustomVoice 模型；VoiceDesign 和克隆模型需要额外参数，不能假装共用同一种调用方式。

## SenseVoice

按照 SenseVoice/FunASR 官方说明创建独立环境，安装 FunASR，并准备本地 SenseVoiceSmall 权重后运行：

```powershell
python .\workers\sensevoice_server.py --model D:\Models\SenseVoiceSmall --device cpu --port 50000
```

在 JARVIS 设置中选择“SenseVoice 本地工作进程”，接口填写：

```text
http://127.0.0.1:50000/v1/audio/transcriptions
```

## CosyVoice3

CosyVoice 官方已经提供 FastAPI、gRPC 和双流式推理，但其原始请求字段并非 OpenAI TTS 格式。推荐在 CosyVoice 独立环境中增加一层很薄的协议适配，将 `/v1/audio/speech` 请求映射到所选的 SFT、zero-shot 或 instruct 推理模式。主程序无需跟随 CosyVoice 内部 API 变动。

正式分发模型包前，必须分别核对代码许可证、模型权重许可证、音色/克隆素材授权、CUDA 运行库再分发条件，并提供 SHA-256 校验。不要把可下载模型的许可证自动等同于可商用或可重新分发。

官方资料：

- https://github.com/QwenLM/Qwen3-TTS
- https://github.com/QwenAudio/SenseVoice
- https://github.com/QwenAudio/CosyVoice
