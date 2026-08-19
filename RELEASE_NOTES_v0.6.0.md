# JARVIS LOCAL 0.6.0

0.6.0 在 0.5.0 实时响应链路上增加可选离线语音工作进程，重点解决高品质模型依赖冲突、模型包分档和 SenseVoice 接入问题。

## 主要变化

- 设置版本升级到 6，STT 新增 `sensevoice` 提供商和独立转写接口地址。
- SenseVoice 使用 OpenAI-compatible multipart 协议接收本机录音，不改变现有 `/api/stt` 浏览器接口。
- 启动预热会访问工作进程 `/health`，区分“已填写地址”和“模型确实已经加载”。
- SenseVoice 可返回语言与情绪标签；情绪只作为经过枚举校验的弱提示加入本轮系统上下文，不写进聊天正文。
- 提供 Qwen3-TTS CustomVoice 和 SenseVoice 的独立参考服务器，主程序、ASR、TTS 可以分别使用不同 Python/CUDA 环境。
- Qwen3-TTS、CosyVoice 继续使用 `/v1/audio/speech`；主程序已有的短句队列可在服务端生成下一句时播放上一句。
- 所有参考服务强制绑定本机回环地址，并限制请求大小、文本长度和响应类型。

## 模型包边界

- 基础离线包继续内置 Kokoro 和 faster-whisper，确保普通 CPU 设备开箱可用。
- Qwen3-TTS、CosyVoice、SenseVoice 作为可选模型包，不在未核对许可证和硬件要求时塞进基础安装包。
- Qwen3-TTS 参考服务面向 `0.6B-CustomVoice`；VoiceDesign、声音克隆和 CosyVoice zero-shot 需要额外授权素材与参数，不能伪装成同一接口能力。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check .\jarvis\static\app.js
.\.venv\Scripts\python.exe -m py_compile jarvis\*.py workers\*.py
```
