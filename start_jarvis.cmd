@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo JARVIS LOCAL has not been set up yet.
  echo Run: powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "desktop.py"
if errorlevel 1 pause
