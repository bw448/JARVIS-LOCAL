# JARVIS LOCAL 0.7.0 当前机器验收报告

验收时间：2026-08-15（Asia/Shanghai）  
发布目录：`D:\jarvis-assistant\dist\JARVIS-LOCAL-0.7.0-Windows-x64-Offline`

## 结论

0.7.0 完整离线目录已构建成功。自动诊断结果为 **PASS 9 / BLOCKED 0 / WARN 0 / NOT_RUN 3 / MANUAL 8**，版本错配问题已经消除，可以进入原生 Windows GUI、麦克风和性能人工验收。

## 已通过

| 检查项 | 结果 |
|---|---|
| 构建运行时 | Python 3.11.9，符合项目版本范围 |
| 包与源码版本 | 均为 0.7.0 |
| Kokoro 与 Whisper | 关键模型文件齐全，合计 812.8 MiB |
| 冻结后 TTS 自检 | 成功生成 259,970 字节 WAV |
| 冻结后 STT 自检 | 成功识别打包测试语音 |
| 电脑控制安全链路 | 白名单、一次性提案和取消流程通过，未执行系统操作 |
| 主程序 | 12.6 MiB；SHA-256 `c573a623e7695abf9349343081c50241240eddb63c025580917b0994e809ce00` |
| 完整目录 | 1,424,115,444 字节（约 1.33 GiB） |
| ZIP 完整性 | Python ZIP CRC 测试通过 |

## 发布文件

- `dist\JARVIS-LOCAL-0.7.0-Windows-x64-Offline.zip`（约 1.1 GiB）
- ZIP SHA-256：`46fbf0b5a4fd79f2fb6ba2186d2eda865a5610352956ff85cc760f9887b8b5e1`
- 包内详细报告：`ACCEPTANCE-REPORT.md`

## 尚未运行

文本模型、Qwen3-TTS 和 SenseVoice 本机服务没有启动，因此三个健康端点标记为 `NOT_RUN`。这不影响默认 Kokoro + faster-whisper 离线语音闭环。

以下项目仍须人工验证：

- 双击 EXE 后窗口启动与悬浮 HUD 显示；
- 改名“贾维斯”后中央不出现“贾”字；
- 真实麦克风的单次录音和连续语音；
- 停止朗读和监听恢复；
- 情绪陪伴回答的自然度；
- 记事本/计算器的确认、取消和单次执行；
- STT、LLM 首字、TTS 首句的真实延迟；
- 完全断网重新启动。

Windows 全量 pytest 输出读取受到桌面工具额度限制，未在本阶段取得新的完整测试记录；此前源码回归为 62 项通过，本次新增验收逻辑的 5 项冒烟测试通过。冻结后真实 TTS/STT 自检和发布包诊断均已通过。
