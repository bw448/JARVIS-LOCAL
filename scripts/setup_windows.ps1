$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VirtualEnv = Join-Path $ProjectRoot ".venv"

$PythonCommand = $null
foreach ($Version in @("3.12", "3.11")) {
    & py "-$Version" -c "import sys; print(sys.version)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $PythonCommand = $Version
        break
    }
}

if (-not $PythonCommand) {
    throw "Python 3.11 or 3.12 was not found. Install 64-bit Python from python.org with the py launcher enabled."
}

if (-not (Test-Path $VirtualEnv)) {
    & py "-$PythonCommand" -m venv $VirtualEnv
}

$PythonExe = Join-Path $VirtualEnv "Scripts\python.exe"
& $PythonExe -m pip install --upgrade pip setuptools wheel
& $PythonExe -m pip install -e "$ProjectRoot[desktop]"

Write-Host ""
Write-Host "JARVIS LOCAL base environment is ready." -ForegroundColor Green
Write-Host "Double-click start_jarvis.cmd to launch it."
Write-Host "For offline speech, run scripts\install_voice.ps1 next."
