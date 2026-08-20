---
name: python-development
description: Python 开发规范，包括代码风格、项目结构、最佳实践
tags: [python, coding, style, development, 开发]
tools_required: [file_tool, cmd_tool]
---

# Python 开发规范

## 代码风格

### PEP 8 规范
- 缩进: 4 空格
- 行宽: 79 字符 (代码), 72 字符 (文档)
- 命名: snake_case (变量/函数), PascalCase (类)
- 导入: 标准库 → 第三方 → 本地

### 类型注解
```python
def greet(name: str, times: int = 1) -> str:
    """问候函数"""
    return f"Hello, {name}! " * times
```

## 项目结构

```
project/
├── README.md
├── pyproject.toml
├── src/
│   └── package/
│       ├── __init__.py
│       ├── module1.py
│       └── module2.py
├── tests/
│   ├── __init__.py
│   ├── test_module1.py
│   └── test_module2.py
└── docs/
```

## 最佳实践

### 虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 依赖管理
```bash
# pyproject.toml
[project]
dependencies = [
    "requests>=2.28",
    "pydantic>=2.0",
]
```

### 测试
```bash
pytest tests/ -v --cov=src
```

---

# 常用模式

## 上下文管理器
```python
from contextlib import contextmanager

@contextmanager
def managed_resource():
    resource = acquire()
    try:
        yield resource
    finally:
        release(resource)
```

## 数据类
```python
from dataclasses import dataclass

@dataclass
class User:
    name: str
    email: str
    age: int = 0
```

## 异步编程
```python
import asyncio

async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
```
