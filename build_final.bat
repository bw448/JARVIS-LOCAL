@echo off
chcp 65001 >nul
echo ========================================
echo    JARVIS LOCAL v1.1.0 完整打包
echo ========================================
echo.

cd /d "%~dp0"

echo [1/5] 清理旧文件...
if exist dist\JARVIS LOCAL rmdir /s /q "dist\JARVIS LOCAL"
if exist build rmdir /s /q build

echo [2/5] 打包独立窗口版本...
python -m PyInstaller desktop.py --name "JARVIS LOCAL" --windowed --noconfirm --add-data "jarvis/static;jarvis/static" --add-data "dist/JARVIS-LOCAL-0.7.0-Windows-x64-Offline/_internal/models;models"

echo [3/5] 复制到 JARVIS-LOCAL 目录...
if exist D:\JARVIS-LOCAL rmdir /s /q D:\JARVIS-LOCAL
mkdir D:\JARVIS-LOCAL
xcopy "dist\JARVIS LOCAL\*" "D:\JARVIS-LOCAL\" /E /I /Y

echo [4/5] 清理临时文件...
rmdir /s /q build
rmdir /s /q "dist\JARVIS LOCAL"

echo [5/5] 完成！
echo.
echo ========================================
echo    JARVIS LOCAL v1.1.0 已安装到:
echo    D:\JARVIS-LOCAL\JARVIS LOCAL.exe
echo ========================================
echo.
echo 双击运行: D:\JARVIS-LOCAL\JARVIS LOCAL.exe
echo.
pause
