# JARVIS LOCAL 优化上下文

## 项目基本信息
- 名称: JARVIS LOCAL v1.1.0
- 定位: 本地优先的个人语音助手
- 语言: Python 3.11+
- 路径: /mnt/d/jarvis-assistant

## 技术栈
- GUI: pywebview
- 语音识别: faster-whisper + 云端备用
- 语音合成: sherpa-onnx + Kokoro + 云端备用
- AI模型: OpenAI-compatible (llama.cpp, Ollama, vLLM)
- 嵌入模型: sentence-transformers
- 多模态: EasyOCR + GPT-4o Vision
- 即时通讯: 微信/飞书
- 打包: PyInstaller

## 核心模块 (19个)

### 基础模块
- jarvis/app.py - 基础应用
- jarvis/app_enhanced.py - 增强版应用
- jarvis/brain.py - AI大脑
- jarvis/speech.py - 本地语音服务
- jarvis/config.py - 配置管理

### P0 模块
- jarvis/voice_enhanced.py - 增强语音系统
- jarvis/memory_vector.py - 向量嵌入记忆
- jarvis/subagent.py - 子代理系统

### P1 模块
- jarvis/voice_stream.py - 实时语音流
- jarvis/web_crawler.py - 网页爬取
- jarvis/web_search.py - 网络搜索

### P2 模块
- jarvis/multimodal.py - 多模态输入
- jarvis/canvas.py - Canvas 工作台
- jarvis/messaging.py - 即时通讯
- jarvis/llm_local.py - 本地 LLM

### 功能模块
- jarvis/memory.py - 基础记忆系统
- jarvis/skills.py - 技能系统
- jarvis/document.py - 文档处理
- jarvis/computer_use.py - 电脑控制
- jarvis/app_integration.py - 功能集成

## 内置技能 (8个)
- code-development - 代码开发
- data-analysis - 数据分析
- file-organization - 文件整理
- git-workflow - Git 工作流
- project-planning - 项目规划
- python-development - Python 开发
- systematic-debugging - 系统化调试
- web-research - 网络研究

## 版本历史
- v0.7.4 - 基础版本
- v0.8.0 - 记忆、技能、搜索、文档
- v0.9.0 - 语音增强、向量记忆、子代理
- v1.0.0 - 语音流、更多技能、网页爬取
- v1.1.0 - 多模态、Canvas、即时通讯、本地LLM (当前)

## 已完成功能 ✅

### P0 高优先级
1. 语音系统增强 - 云端ASR/TTS备用
2. 向量嵌入记忆 - 语义搜索
3. 子代理系统 - 异步任务执行

### P1 中优先级
4. 实时语音流 - WebSocket双向通信
5. 内置技能库 - 8个专业技能
6. 网页爬取 - 内容提取、知识库

### P2 低优先级
7. 多模态输入 - 图片理解、OCR
8. Canvas 工作台 - 代码/图表/表格
9. 即时通讯 - 微信/飞书集成
10. 本地 LLM - llama.cpp/Ollama/vLLM

## 后续优化方向
- 性能优化
- 更多语言支持
- 移动端适配
- 云端同步

## 参考项目
- Aivy OS: /mnt/d/迅雷下载/Aivy OS

## 环境配置
- WSL bash 已配置
- Codex 可正常执行命令
- Python 3.14.4 可用
