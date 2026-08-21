@echo off
chcp 65001 >nul
echo ========================================
echo    JARVIS LOCAL v1.2.0 构建脚本
echo    (含 DeepSeek Harness 集成)
echo ========================================
echo.

cd /d "%~dp0"

echo [1/5] 安装 DeepSeek Harness SDK...
pip install deepseek-harness-sdk --quiet 2>nul
if errorlevel 1 (
    echo [警告] DeepSeek Harness SDK 安装失败，将使用 OpenAI 兼容模式
)

echo [2/5] 清理旧构建...
if exist build rmdir /s /q build
if exist "dist\JARVIS LOCAL" rmdir /s /q "dist\JARVIS LOCAL"
if exist "dist\JARVIS-LOCAL" rmdir /s /q "dist\JARVIS-LOCAL"

echo [3/5] 使用 PyInstaller 打包（包含语音模型）...
python -m PyInstaller --noconfirm --clean ^
    --workpath build ^
    --distpath dist ^
    packaging\jarvis_offline.spec

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！请检查上面的错误信息。
    pause
    exit /b 1
)

echo [4/5] 同步到 JARVIS-LOCAL 运行目录...
if exist D:\JARVIS-LOCAL\JARVIS.LOCAL.exe del /f "D:\JARVIS-LOCAL\JARVIS.LOCAL.exe"
xcopy "dist\JARVIS-LOCAL\*" "D:\JARVIS-LOCAL\" /E /I /Y

echo [5/5] 清理构建临时文件...
rmdir /s /q build

echo.
echo ========================================
echo    构建完成！
echo    
echo    大脑模式: DeepSeek Harness (首选)
echo              OpenAI 兼容 (备选)
echo    
echo    运行: D:\JARVIS-LOCAL\JARVIS LOCAL.exe
echo ========================================
echo.
pause
