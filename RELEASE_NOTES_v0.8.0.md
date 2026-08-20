# JARVIS LOCAL v0.8.0 Release Notes

**发布日期**: 2026-08-20  
**版本**: 0.8.0  
**代号**: Enhanced Intelligence

---

## 🎉 重大更新

### 1. 记忆系统 (Memory System)
参考 Aivy OS 的记忆架构，实现了完整的三层记忆系统：

- **核心记忆** (Core Memory)
  - 始终包含在 AI 上下文中的关键信息
  - 自动记住用户姓名、偏好等
  - 最多 30 条核心记忆

- **短期记忆** (Short-term Memory)
  - 最近的对话历史
  - 自动维护对话连贯性
  - 最多 50 轮对话

- **长期记忆** (Long-term Memory)
  - 可搜索的知识库
  - 自动提取用户偏好和事实
  - 基于关键词的智能检索

### 2. 技能系统 (Skills System)
参考 Aivy OS 的技能架构，实现了可扩展的技能系统：

- **SKILL.md 格式**: 使用 Markdown 定义技能
- **自动加载**: 从 skills/ 目录自动加载
- **技能搜索**: 根据名称、描述、标签搜索技能
- **内置技能**:
  - 代码开发规范
  - 网络研究方法
  - 数据分析流程

### 3. 网络搜索 (Web Search)
为 AI 添加了互联网搜索能力：

- **多引擎支持**: DuckDuckGo、Bing、Serper
- **智能格式化**: 自动格式化搜索结果供 AI 理解
- **工具集成**: 作为 AI 工具可直接调用

### 4. 文档处理 (Document Processing)
实现了基本的文档读写能力：

- **文本文件**: .txt, .md, .py, .js, .json 等
- **PDF 支持**: 需要安装 pdfminer
- **DOCX 支持**: 需要安装 python-docx
- **XLSX 支持**: 需要安装 pandas + openpyxl

### 5. UI 增强
参考 Aivy OS 的玻璃态设计：

- **玻璃态效果**: 半透明背景 + 模糊效果
- **发光边框**: 鼠标悬停时的光效
- **新面板**: 记忆面板、技能面板
- **快速操作**: 工具栏快捷按钮
- **版本显示**: 右下角版本徽章

---

## 📦 新增文件

```
jarvis/
├── memory.py          # 记忆系统
├── skills.py          # 技能系统
├── web_search.py      # 网络搜索
├── document.py        # 文档处理
├── app_integration.py # 功能集成
└── skills/            # 内置技能目录
    ├── code-development/SKILL.md
    ├── web-research/SKILL.md
    └── data-analysis/SKILL.md
```

---

## 🔧 API 端点

### 新增 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/stats` | GET | 获取系统统计信息 |
| `/api/memory/stats` | GET | 获取记忆统计 |
| `/api/memory/remember` | POST | 存储长期记忆 |
| `/api/memory/recall` | POST | 搜索记忆 |
| `/api/skills` | GET | 获取技能列表 |
| `/api/search` | POST | 网络搜索 |

### 工具定义

AI 现在可以使用以下工具：

- `web_search` - 搜索互联网
- `memory_store` - 存储记忆
- `memory_recall` - 回忆信息
- `read_file` - 读取文件
- `write_file` - 写入文件
- `list_directory` - 列出目录

---

## 🚀 使用方法

### 启动增强版服务器

```bash
python run_enhanced.py
# 或
python run_enhanced.py --port 8080
```

### 让 AI 记住信息

对话中直接告诉 AI：
- "记住我喜欢喝咖啡"
- "我的名字是张先生"
- "记住我住在上海"

### 使用搜索功能

AI 会自动使用搜索功能，或者你可以直接要求：
- "搜索 Python 教程"
- "帮我查一下今天的新闻"

---

## 📝 依赖说明

### 必需依赖
- Python 3.11+
- 标准库 (json, threading, pathlib 等)

### 可选依赖 (增强功能)
```bash
# PDF 支持
pip install pdfminer.six

# DOCX 支持
pip install python-docx

# XLSX 支持
pip install pandas openpyxl
```

---

## 🙏 致谢

本版本参考了 [Aivy OS](https://github.com/aivyos) 的以下设计：
- 记忆系统架构
- 技能系统设计
- UI 玻璃态风格

---

## 📋 下一步计划

- [ ] 向量嵌入支持 (更智能的记忆搜索)
- [ ] 技能热加载
- [ ] 多模态输入 (图片、音频)
- [ ] 子代理系统
- [ ] 更多内置技能

---

**完整更新日志**: [CHANGELOG.md](CHANGELOG.md)
