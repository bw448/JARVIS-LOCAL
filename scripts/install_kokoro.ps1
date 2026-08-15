$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "The base environment is missing. Run scripts\setup_windows.ps1 first."
}

Write-Host "Installing the optional Kokoro speech component..." -ForegroundColor Cyan
& $PythonExe -m pip install -e "$ProjectRoot[kokoro]"
if ($LASTEXITCODE -ne 0) {
    throw "Kokoro installation failed."
}

Write-Host "Kokoro is installed. Its upstream package obtains model weights when first used." -ForegroundColor Green
Write-Host "Select Kokoro in JARVIS LOCAL speech settings."
