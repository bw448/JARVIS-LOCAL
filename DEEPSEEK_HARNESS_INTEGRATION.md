# DeepSeek Harness 集成指南

## 概述

JARVIS 现已支持 DeepSeek Harness Python SDK 集成，可以将 DeepSeek Harness 的插件式智能体架构作为 JARVIS 的底层大脑。

## 架构说明

```
┌─────────────────────────────────────────────────────────┐
│                      JARVIS 应用层                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │   语音系统   │  │   UI 界面   │  │   记忆系统   │      │
│  └─────────────┘  └─────────────┘  └─────────────┘      │
├─────────────────────────────────────────────────────────┤
│                     HybridBrain 适配层                    │
│  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ OpenAI兼容大脑   │  │  DeepSeek Harness 大脑      │  │
│  │  (本地/在线LLM)  │  │  (插件式智能体架构)        │  │
│  └─────────────────┘  └─────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                    DeepSeek Harness 运行时                │
│  ┌─────────────────────────────────────────────────────┐│
│  │  Cordis 插件系统 | 工具注册 | 会话管理 | 子代理    ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

## 安装

### 1. 安装 DeepSeek Harness SDK

```bash
# 方法1: 使用安装脚本
./scripts/setup_deepseek_harness.sh

# 方法2: 手动安装
pip install deepseek-harness-sdk
```

### 2. 配置 JARVIS

在 JARVIS 设置中添加 DeepSeek Harness 配置:

```json
{
    "dsh": {
        "enabled": true,
        "model": "deepseek-chat",
        "provider": "deepseek-official",
        "api_key": "your-api-key-here",
        "base_url": "",  // 可选，自定义API地址
        "request_timeout": 120.0,
        "shutdown_timeout": 2.0
    }
}
```

## 配置选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | false | 启用/禁用 DeepSeek Harness |
| `model` | string | "deepseek-chat" | 使用的模型名称 |
| `provider` | string | "deepseek-official" | 模型提供商 |
| `api_key` | string | "" | API 密钥 |
| `base_url` | string | "" | 自定义 API 基础 URL |
| `max_tokens` | int | null | 最大 token 数 |
| `runtime_bin` | string | "" | 自定义运行时二进制路径 |
| `session_root` | string | "" | 会话存储路径 |
| `cordis_config` | string | "" | 自定义 Cordis 配置路径 |
| `request_timeout` | float | 120.0 | 请求超时时间(秒) |
| `shutdown_timeout` | float | 2.0 | 关闭超时时间(秒) |
| `env_overrides` | dict | {} | 环境变量覆盖 |

## 使用方式

### 自动切换

当 `dsh.enabled = true` 时，JARVIS 会自动使用 DeepSeek Harness 作为大脑。如果 DeepSeek Harness 不可用或出错，会自动回退到 OpenAI 兼容大脑。

### 手动切换

在代码中可以显式指定使用哪个大脑:

```python
from jarvis.brain_deepseek import DeepSeekHarnessBrain, DSHBrainConfig

# 创建 DeepSeek Harness 大脑
config = DSHBrainConfig(enabled=True, model="deepseek-chat")
brain = DeepSeekHarnessBrain(config)

# 使用它
response = brain.complete(settings, messages)
```

## 离线运行

### 方案1: 固定版本

```bash
# 克隆特定版本
git clone --depth 1 --branch v0.x.x https://github.com/deepseek-ai/deepseek-harness.git
cd deepseek-harness

# 安装离线依赖
pip install -e python/sdk
pip install -e python/sdk-runtime
```

### 方案2: 离线包

```bash
# 下载 wheel 包
pip download deepseek-harness-sdk -d ./offline-packages

# 离线安装
pip install --no-index --find-links=./offline-packages deepseek-harness-sdk
```

### 方案3: 本地运行时

配置 `runtime_bin` 指向本地构建的运行时:

```json
{
    "dsh": {
        "runtime_bin": "/path/to/local/dsh-jsonrpc-agent"
    }
}
```

## 插件开发

### 创建自定义插件

DeepSeek Harness 使用 Cordis 插件系统。创建插件的基本步骤:

1. 创建插件目录结构
2. 实现插件接口
3. 注册到 Cordis 上下文

```typescript
// 示例插件结构
export default function myPlugin(ctx: Context) {
    // 注册工具
    ctx.tools.register({
        name: 'my_tool',
        description: 'My custom tool',
        parameters: { /* ... */ },
        execute: async (params) => {
            // 工具实现
        }
    });
}
```

### 插件市场

- 官方插件: 使用 `dsh-plugin` 话题标签在 GitHub 搜索
- 自建插件市场: 创建 GitHub 仓库，配置插件源

## 故障排除

### 常见问题

1. **DeepSeek Harness SDK 未安装**
   ```
   解决: pip install deepseek-harness-sdk
   ```

2. **运行时未找到**
   ```
   解决: 安装 deepseek-harness-runtime-bin 或配置 runtime_bin
   ```

3. **API 密钥错误**
   ```
   解决: 检查 dsh.api_key 或 DEEPSEEK_API_KEY 环境变量
   ```

4. **连接超时**
   ```
   解决: 增加 dsh.request_timeout 或检查网络
   ```

## 参考资料

- [DeepSeek Harness 官方文档](https://github.com/deepseek-ai/deepseek-harness)
- [Python SDK 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md)
- [架构文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md)
