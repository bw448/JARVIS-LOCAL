@echo off
setlocal
cd /d "%~dp0"
echo Installing the bundled Microsoft Edge WebView2 Runtime...
"MicrosoftEdgeWebView2RuntimeInstallerX64.exe" /silent /install
if errorlevel 1 (
  echo WebView2 installation failed with error %errorlevel%.
  pause
  exit /b 1
)
echo WebView2 installation completed.
pause
