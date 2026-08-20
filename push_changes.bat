@echo off
echo ========================================
echo JARVIS Assistant - 推送更改到远程仓库
echo ========================================
echo.

cd /d D:\jarvis-assistant

echo 当前 Git 状态:
git status
echo.

echo 提交更改...
git add -A
git commit -m "v0.7.4: 语音模式优化界面优化功能扩展"
echo.

echo 推送到远程仓库...
git push
echo.

echo 完成!
pause
