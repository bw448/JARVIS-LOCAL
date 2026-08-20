@echo off
echo ========================================
echo    完整打包 JARVIS LOCAL v1.1.0
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] 清理旧文件...
if exist dist\JARVIS LOCAL rmdir /s /q "dist\JARVIS LOCAL"
if exist build rmdir /s /q build

echo [2/3] 开始打包...
python -m PyInstaller run.py ^
    --name "JARVIS LOCAL" ^
    --windowed ^
    --noconfirm ^
    --add-data "jarvis/static;jarvis/static" ^
    --add-data "dist/JARVIS-LOCAL-0.7.0-Windows-x64-Offline/_internal/models;models"

echo [3/3] 完成！
echo.
echo 新的 EXE 在: dist\JARVIS LOCAL\JARVIS LOCAL.exe
echo.
pause
