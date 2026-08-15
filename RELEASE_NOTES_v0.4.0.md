# JARVIS LOCAL 0.4.0

JARVIS LOCAL 是一款本地优先的 Windows x64 私人语音助手。完整离线包已内置本机语音合成和语音识别模型，解压后可直接运行。

## 下载

下载 `JARVIS-LOCAL-0.4.0-Windows-x64-Offline.zip`，完整解压后双击 `JARVIS LOCAL.exe`。不要只单独移动 EXE，`_internal` 目录是必需的运行组件。

## 主要功能

- 本地 Kokoro 中文语音合成，内置多个女声音色；
- 本地 faster-whisper 语音识别；
- 连续语音对话、单次说话与文字交互；
- 可连接 OpenAI-compatible 文本模型接口；
- Windows 原生透明悬浮 HUD 和多套外观主题；
- 个人配置保存在 `%LOCALAPPDATA%\JarvisAssistant`，API 密钥使用 Windows 凭据管理器。

## 系统要求

- Windows 10/11 x64；
- 建议至少 4 GB 可用内存；
- 文本模型服务由用户自行配置，本地语音功能不需要联网；
- Windows 11 通常已包含 WebView2。如窗口无法显示，运行 `Prerequisites\INSTALL_WEBVIEW2.cmd`。

## 完整性校验

下载同名 `.sha256` 文件后，可在 PowerShell 中执行：

```powershell
Get-FileHash .\JARVIS-LOCAL-0.4.0-Windows-x64-Offline.zip -Algorithm SHA256
```

计算结果应与 `.sha256` 文件中的值一致。

## 已知提示

- 当前版本未使用商业代码签名证书，Windows SmartScreen 可能显示“未知发布者”；
- 请从本 GitHub Release 下载并核对 SHA-256；
- 第三方组件、语音模型及其许可信息见包内 `THIRD_PARTY_NOTICES.md`。
