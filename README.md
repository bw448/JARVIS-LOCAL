<div align="center">

<img src="https://raw.githubusercontent.com/bw448/JARVIS-LOCAL/main/assets/jarvis-app-icon-3d-v3.png" width="160" alt="JARVIS LOCAL Logo">

# JARVIS LOCAL

**本地优先的 AI 语音助手 · 完全离线运行 · 你的私人 JARVIS**

</div>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.2.0-cyan?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/python-3.11+-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=for-the-badge&logo=windows&logoColor=white" alt="Platform">
</p>

<p align="center">
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-功能特性">功能特性</a> ·
  <a href="#-技术栈">技术栈</a> ·
  <a href="#-许可证">许可证</a>
</p>

---

## 🖥️ 界面预览

<div align="center">

**主界面 — 深色科技风 HUD**

![主界面](https://raw.githubusercontent.com/bw448/JARVIS-LOCAL/main/assets/ui-preview.png)

<br>

**语音模式 — 沉浸式语音交互**

![语音模式](https://raw.githubusercontent.com/bw448/JARVIS-LOCAL/main/assets/voice-mode-preview.png)

</div>

---

## ✨ 核心亮点

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🔒 本地优先，隐私无忧</h3>
      <p>所有语音处理、模型推理均在本地完成，<strong>零数据上传</strong>。你的对话只属于你。</p>
    </td>
    <td width="50%" valign="top">
      <h3>🎤 全语音交互</h3>
      <p>支持连续语音对话，说完自动识别发送。<strong>真正的免提体验</strong>，像和真人助手一样自然。</p>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>🧠 智能体架构</h3>
      <p>基于 <strong>DeepSeek Harness</strong> 的插件式智能体，HybridBrain 自动切换模型，支持本地 LLM。</p>
    </td>
    <td width="50%" valign="top">
      <h3>⚡ 8 大技能系统</h3>
      <p>代码开发、数据分析、文件管理、Git 工作流、项目规划、系统调试、网络调研……开箱即用。</p>
    </td>
  </tr>
</table>

---

## 🎯 功能特性

### 🗣️ 语音交互
| 功能 | 说明 |
|------|------|
| **语音识别 (STT)** | faster-whisper 本地识别，支持中英文 |
| **语音合成 (TTS)** | sherpa-onnx + Kokoro，中文通过 misaki 引擎 |
| **连续语音** | 说完自动识别发送，无需点击按钮 |
| **语音模式** | 全屏 HUD 沉浸式语音交互界面 |

### 🤖 AI 智能体
| 功能 | 说明 |
|------|------|
| **DeepSeek Harness** | 插件式智能体架构，可扩展能力强 |
| **HybridBrain** | 自动在 DeepSeek Harness 和 OpenAI 兼容接口间切换 |
| **本地 LLM** | 支持本地大模型推理，无需联网 |
| **子代理系统** | 复杂任务自动拆分，并行执行 |

### 📚 知识管理
| 功能 | 说明 |
|------|------|
| **向量记忆** | 嵌入语义搜索，记住对话上下文 |
| **网页搜索** | DuckDuckGo、Bing 多引擎搜索 |
| **网页爬取** | 自动抓取网页内容，构建本地知识库 |
| **文档处理** | 支持 PDF、DOCX、XLSX 文件解析 |

### 🖥️ 系统控制
| 功能 | 说明 |
|------|------|
| **电脑操控** | 自动化操作电脑，执行复杂任务 |
| **Canvas 工作台** | 可视化工作空间 |
| **文件管理** | 智能文件整理与操作 |
| **桌面 HUD** | pywebview 桌面应用，悬浮窗实时状态 |

---

## 🚀 快速开始

### 方式一：下载离线包（推荐）

从 [Releases](https://github.com/bw448/JARVIS-LOCAL/releases) 下载最新版本，解压后直接运行 `JARVIS LOCAL.exe`。

> 💡 无需安装 Python，无需配置环境，开箱即用。

### 方式二：从源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/bw448/JARVIS-LOCAL.git
cd JARVIS-LOCAL

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python run.py
```

### 方式三：配置向导

首次运行后，执行配置向导设置 API Key 和偏好：

```bash
python -m jarvis.settings_manager
```

---

## 📦 技术栈

| 类别 | 技术 |
|------|------|
| **语言** | Python 3.11 - 3.13 |
| **语音识别** | faster-whisper |
| **语音合成** | sherpa-onnx, Kokoro, misaki |
| **AI 框架** | DeepSeek Harness, OpenAI 兼容接口 |
| **向量搜索** | NumPy, 嵌入模型 |
| **桌面 UI** | pywebview, HTML/CSS/JS |
| **打包** | PyInstaller (Windows) |
| **搜索** | DuckDuckGo, Bing |

---

## 📁 项目结构

```
JARVIS-LOCAL/
├── jarvis/                # 核心包
│   ├── app.py             # 主应用
│   ├── speech.py          # 语音引擎
│   ├── brain_deepseek.py  # DeepSeek 智能体
│   ├── memory_vector.py   # 向量记忆
│   ├── computer.py        # 电脑控制
│   ├── plugins/           # 插件系统
│   ├── skills/            # 8 大技能
│   └── static/            # Web 前端
├── assets/                # 图标和截图
├── scripts/               # 构建脚本
├── tests/                 # 测试
└── run.py                 # 入口文件
```

---

## 🤝 许可证

[MIT License](LICENSE) — 自由使用，自由修改，自由分享。

---

<p align="center">
  <strong>⚡ JARVIS LOCAL — 你的私人 AI 助手，本地运行，隐私无忧。</strong>
</p>
