@echo off
chcp 65001 >nul
echo ========================================
echo    JARVIS v1.2.0 完整构建脚本
echo ========================================
echo.

cd /d "%~dp0"

echo [1/5] 创建虚拟环境...
if not exist .venv (
    py -3.9 -m venv .venv
)

echo [2/5] 激活虚拟环境...
call .venv\Scripts\activate.bat

echo [3/5] 安装所有依赖...
pip install --upgrade pip
pip install pydantic keyring pyinstaller
pip install sherpa-onnx kokoro misaki[zh] numpy soundfile faster-whisper
pip install pywebview Pillow

echo [4/5] 构建 exe...
python -m PyInstaller --noconfirm --clean packaging\jarvis_offline.spec

echo [5/5] 复制到 JARVIS-LOCAL...
copy "dist\JARVIS-LOCAL\JARVIS LOCAL.exe" "D:\JARVIS-LOCAL\"

echo.
echo ========================================
echo    构建完成！
echo    运行: D:\JARVIS-LOCAL\JARVIS LOCAL.exe
echo ========================================
echo.
pause
