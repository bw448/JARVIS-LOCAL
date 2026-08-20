# JARVIS Assistant - 构建并推送更改
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "JARVIS Assistant - 构建并推送更改" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 切换到项目目录
Set-Location "D:\jarvis-assistant"

# 检查 Git 状态
Write-Host "检查 Git 状态..." -ForegroundColor Yellow
git status
Write-Host ""

# 提交更改
Write-Host "提交更改..." -ForegroundColor Yellow
git add -A
git commit -m "v0.7.4: 语音模式优化界面优化功能扩展"
Write-Host ""

# 推送到远程仓库
Write-Host "推送到远程仓库..." -ForegroundColor Yellow
git push
Write-Host ""

# 运行构建脚本
Write-Host "运行构建脚本..." -ForegroundColor Yellow
.\scripts\build_offline_windows.ps1
Write-Host ""

Write-Host "完成!" -ForegroundColor Green
Read-Host "按 Enter 键退出"
