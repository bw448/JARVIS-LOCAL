# JARVIS LOCAL

**本地优先的个人语音助手** - v1.1.0

[![Version](https://img.shields.io/badge/version-1.1.0-blue)](https://github.com/your-repo/jarvis-local)
[![Python](https://img.shields.io/badge/python-3.11+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

---

## ✨ 特性

### 🎤 语音系统
- **本地语音识别** - faster-whisper 离线识别
- **本地语音合成** - sherpa-onnx + Kokoro 多音色
- **云端备用** - Qwen Audio、OpenAI Whisper/TTS
- **实时语音流** - WebSocket 双向通信
- **连续语音** - 打断支持、静音检测

### 🧠 记忆系统
- **向量嵌入** - 语义搜索，不再只是关键词匹配
- **三层记忆** - 核心记忆、短期记忆、长期记忆
- **自动提取** - 从对话中自动提取重要信息

### 🔧 技能系统
- **8 个内置技能** - 代码开发、调试、规划、Git 等
- **SKILL.md 格式** - Markdown 定义，易于扩展
- **自动匹配** - 根据任务自动选择相关技能

### 🔍 搜索与爬取
- **网络搜索** - DuckDuckGo、Bing、Serper
- **网页爬取** - 内容提取、知识库构建
- **文档处理** - PDF、DOCX、XLSX 支持

### 🖼️ 多模态
- **图片理解** - OCR 文字识别、视觉分析
- **Canvas 工作台** - 代码、图表、表格可视化

### 💬 即时通讯
- **微信集成** - WebSocket 机器人
- **飞书集成** - API/Webhook 支持

### 🤖 AI 增强
- **子代理系统** - 异步任务执行
- **本地 LLM** - llama.cpp、Ollama、vLLM 集成

---

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-repo/jarvis-local.git
cd jarvis-local

# 安装依赖
pip install -e ".[voice-full,desktop]"
```

### 运行

```bash
# 启动增强版
python run_enhanced.py

# 或启动基础版
python run.py
```

### 打包

```bash
# Windows 打包
python scripts/build_offline_windows.ps1
```

---

## 📦 依赖

### 核心依赖
```
Python >= 3.11
```

### 可选依赖
```bash
# 语音功能
pip install sherpa-onnx faster-whisper kokoro misaki[zh]

# 桌面 GUI
pip install pywebview Pillow

# 向量嵌入
pip install sentence-transformers

# OCR
pip install easyocr

# WebSocket
pip install websocket-client

# 文档处理
pip install pdfminer.six python-docx pandas openpyxl
```

---

## 📁 项目结构

```
jarvis/
├── __init__.py          # 包初始化
├── app.py               # 基础应用
├── app_enhanced.py      # 增强应用
├── app_integration.py   # 功能集成
├── brain.py             # AI 大脑
├── speech.py            # 语音服务
├── config.py            # 配置管理
├── memory.py            # 记忆系统
├── memory_vector.py     # 向量记忆
├── skills.py            # 技能系统
├── web_search.py        # 网络搜索
├── web_crawler.py       # 网页爬取
├── document.py          # 文档处理
├── computer_use.py      # 电脑控制
├── voice_enhanced.py    # 增强语音
├── voice_stream.py      # 语音流
├── subagent.py          # 子代理
├── multimodal.py        # 多模态
├── canvas.py            # Canvas
├── messaging.py         # 即时通讯
├── llm_local.py         # 本地 LLM
├── static/              # 前端文件
└── skills/              # 技能库
    ├── code-development/
    ├── data-analysis/
    ├── file-organization/
    ├── git-workflow/
    ├── project-planning/
    ├── python-development/
    ├── systematic-debugging/
    └── web-research/
```

---

## 🔧 配置

### 语音配置

```python
from jarvis.voice_enhanced import VoiceConfig

config = VoiceConfig(
    local_asr_enabled=True,
    local_tts_enabled=True,
    cloud_asr_enabled=True,
    cloud_provider="qwen",
    cloud_api_key="your-api-key",
    wake_word="贾维斯"
)
```

### LLM 配置

```python
from jarvis.llm_local import LLMConfig

config = LLMConfig(
    provider="ollama",
    ollama_model="llama2"
)
```

---

## 📊 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| v1.1.0 | 2026-08-20 | 多模态、Canvas、即时通讯、本地LLM |
| v1.0.0 | 2026-08-20 | 语音流、技能库、网页爬取 |
| v0.9.0 | 2026-08-20 | 语音增强、向量记忆、子代理 |
| v0.8.0 | 2026-08-20 | 记忆、技能、搜索、文档 |
| v0.7.4 | 2026-08-14 | 基础版本 |

---

## 🙏 致谢

- [Aivy OS](https://github.com/aivyos) - 架构参考
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - 语音识别
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) - 语音合成
- [sentence-transformers](https://github.com/UKPLab/sentence-transformers) - 向量嵌入

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

---

## 🔗 链接

- [文档](https://github.com/your-repo/jarvis-local/wiki)
- [问题反馈](https://github.com/your-repo/jarvis-local/issues)
- [发布说明](RELEASE_NOTES_v1.1.0.md)
