# JARVIS LOCAL v1.2.0 发布说明

**发布日期**: 2026-08-21

## 🚀 重大更新：DeepSeek Harness 集成

### 新特性

- **DeepSeek Harness 大脑支持**：集成 DeepSeek Harness Python SDK 作为首选智能体框架
- **插件式架构**：通过 DeepSeek Harness 获得 Cordis 插件系统支持
- **自动回退机制**：DSH 不可用时自动切换到 OpenAI 兼容大脑
- **混合大脑系统**：`HybridBrain` 智能管理两个大脑的切换

### 配置更新

新增 `dsh` 配置块：

```json
{
    "dsh": {
        "enabled": true,
        "model": "deepseek-chat",
        "provider": "deepseek-official",
        "api_key": "your-api-key",
        "fallback_to_openai": true
    }
}
```

### 依赖更新

- 新增 `deepseek-harness-sdk>=0.1.0` 可选依赖
- 新增 `pydantic>=2.12` 核心依赖
- 版本号升级至 1.2.0

### 架构变更

```
JARVIS v1.2.0 架构:

┌─────────────────────────────────────┐
│           JARVIS 应用层              │
├─────────────────────────────────────┤
│         HybridBrain 适配层           │
│  ┌─────────────┐ ┌────────────────┐ │
│  │ OpenAI 大脑  │ │ DSH 大脑       │ │
│  └─────────────┘ └────────────────┘ │
├─────────────────────────────────────┤
│       DeepSeek Harness 运行时       │
│       (Cordis 插件系统)             │
└─────────────────────────────────────┘
```

### 使用说明

1. **自动启用**：默认启用 DSH，需要安装 SDK
2. **手动禁用**：设置 `dsh.enabled = false`
3. **离线运行**：固定版本后离线安装 SDK

### 安装命令

```bash
# 安装完整版（含 DSH）
pip install -e ".[all]"

# 仅安装 DSH
pip install deepseek-harness-sdk
```

### 已知问题

- DSH SDK 首次安装需要网络连接
- 部分 DSH 插件可能需要额外配置

### 下一步计划

- 完善 DSH 插件生态
- 优化 DSH 启动速度
- 添加更多 DSH 配置选项
