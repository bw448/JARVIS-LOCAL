---
name: file-organization
description: 文件整理方法论，包括分类、重命名、清理、备份策略
tags: [file, organization, cleanup, management, 文件, 整理]
tools_required: [file_tool, cmd_tool]
---

# 文件整理规范

## 分类原则

### 按类型分类
```
documents/      # 文档
├── pdf/
├── docx/
└── txt/
images/         # 图片
├── photos/
├── screenshots/
└── icons/
code/           # 代码
├── python/
├── javascript/
└── scripts/
archives/       # 压缩包
```

### 按项目分类
```
projects/
├── project-a/
│   ├── src/
│   ├── docs/
│   └── assets/
└── project-b/
```

### 按时间分类
```
2024/
├── 01-January/
├── 02-February/
└── ...
```

## 命名规范

### 文件命名
- 使用小写字母和连字符
- 包含日期: `2024-01-15-report.pdf`
- 版本号: `document-v1.2.docx`
- 避免特殊字符和空格

### 目录命名
- 简洁明了
- 使用英文
- 避免过深嵌套

## 清理策略

### 定期清理
- 临时文件: `/tmp`, `*.tmp`
- 缓存文件: `__pycache__`, `.cache`
- 日志文件: `*.log`, 超过 30 天

### 归档策略
- 超过 1 年未访问 → 归档
- 项目完成 → 打包归档
- 重要文件 → 备份

## 备份策略

### 3-2-1 原则
- 3 份副本
- 2 种介质
- 1 份异地

### 备份工具
```bash
# rsync
rsync -av --delete source/ destination/

# tar
tar -czf backup.tar.gz directory/

# rclone (云存储)
rclone sync source remote:bucket
```

---

# 整理检查清单

- [ ] 删除临时文件
- [ ] 清理空目录
- [ ] 统一命名规范
- [ ] 移动错放文件
- [ ] 归档旧文件
- [ ] 更新索引/README
