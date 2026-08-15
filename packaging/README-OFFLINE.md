# JARVIS LOCAL 0.4.0 完整离线语音版

## 启动

解压整个文件夹后，双击 `JARVIS LOCAL.exe`。不要只把 EXE 单独移动到其他位置；`_internal` 目录包含程序运行库、晓晓语音模型和本机识别模型。

首次打开后进入“设置”：

1. 智能体名字、主人称呼和回答风格可以自由修改；
2. 语音合成默认是“晓晓 · 甜美女声”，也可以直接试听晓妮、晓伊、晓北；
3. 打开左侧“连续语音”后，说完自动识别和发送，回答结束后自动继续监听；
4. 可选择是否在任务完成时主动播报；
5. 外观页可以切换四套配色、实时调节整个主窗口与悬浮窗各自的透明度；原生透明矢量 HUD 启动时完整显示，拖到边缘后才会吸边收起；
6. “文字模型 API”只需填写一个 OpenAI-compatible 文本模型接口。

语音合成和语音识别完全在本机运行，不需要语音 API，也不需要再次下载模型。Ollama 不是运行条件；文本模型接口是否需要联网取决于你配置的服务。

## 包内组件

- JARVIS LOCAL 0.4.0 Windows x64；
- sherpa-onnx + `kokoro-multi-lang-v1_0`；
- faster-whisper + `Systran/faster-whisper-small`；
- Python 运行环境及应用依赖；
- WebView2 x64 离线安装程序，位于 `Prerequisites`。

Windows 11 通常已经包含 WebView2。如果双击后没有显示窗口，请运行 `Prerequisites\INSTALL_WEBVIEW2.cmd`，安装完成后重新打开程序；该安装过程不需要联网。

## 数据与隐私

个人配置保存在 `%LOCALAPPDATA%\JarvisAssistant`。模型 API 密钥进入 Windows 凭据管理器，不写入发布包或普通配置文件。会话正文默认不保存。

## 注意

本发布包未使用商业代码签名证书。Windows SmartScreen 首次运行时可能显示未知发布者提示；请核对同目录提供的 SHA-256 校验文件。第三方组件说明见 `THIRD_PARTY_NOTICES.md`。
