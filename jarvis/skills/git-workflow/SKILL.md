---
name: git-workflow
description: Git 工作流规范，包括分支管理、提交规范、代码审查
tags: [git, version, control, workflow, 版本控制]
tools_required: [cmd_tool]
---

# Git 工作流规范

## 分支策略

### 分支类型
- `main` - 生产分支，始终可部署
- `develop` - 开发分支，集成最新功能
- `feature/*` - 功能分支，开发新功能
- `hotfix/*` - 热修复分支，紧急修复
- `release/*` - 发布分支，准备发布

### 命名规范
```
feature/user-authentication
feature/payment-integration
hotfix/login-crash
release/v1.2.0
```

## 提交规范

### Conventional Commits
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Type 类型
- `feat` - 新功能
- `fix` - 修复
- `docs` - 文档
- `style` - 格式
- `refactor` - 重构
- `test` - 测试
- `chore` - 构建/工具

### 示例
```
feat(auth): add OAuth2 login support

- Implement Google OAuth2 provider
- Add token refresh mechanism
- Update user profile handling

Closes #123
```

## 代码审查

### 审查要点
- 功能正确性
- 代码风格一致性
- 测试覆盖率
- 安全性考虑
- 性能影响

### 审查流程
1. 创建 Pull Request
2. 填写描述和变更说明
3. 指定审查者
4. 处理审查意见
5. 合并分支

---

# 常用命令

```bash
# 创建功能分支
git checkout -b feature/new-feature

# 提交更改
git add .
git commit -m "feat: add new feature"

# 推送分支
git push origin feature/new-feature

# 合并到 develop
git checkout develop
git merge feature/new-feature

# 删除已合并分支
git branch -d feature/new-feature
```
