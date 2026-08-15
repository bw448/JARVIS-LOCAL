param(
    [switch]$DownloadModels
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ModelFolder = "kokoro-multi-lang-v1_0"
$ModelArchiveUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2"

if (-not (Test-Path $PythonExe)) {
    throw "The base environment is missing. Run scripts\setup_windows.ps1 first."
}

function Confirm-Download {
    param([string]$Prompt)
    if ($DownloadModels) {
        return $true
    }
    $Answer = Read-Host "$Prompt [Y/n]"
    return [string]::IsNullOrWhiteSpace($Answer) -or $Answer.Trim().ToLowerInvariant() -in @("y", "yes")
}

function Test-KokoroModel {
    param([string]$Path)
    $ModelFile = Join-Path $Path "model.onnx"
    $Int8ModelFile = Join-Path $Path "model.int8.onnx"
    $TokensFile = Join-Path $Path "tokens.txt"
    $VoicesFile = Join-Path $Path "voices.bin"
    $ChineseLexicon = Join-Path $Path "lexicon-zh.txt"
    $EspeakData = Join-Path $Path "espeak-ng-data"
    $LicenseFile = Join-Path $Path "LICENSE"
    return ((Test-Path $ModelFile) -or (Test-Path $Int8ModelFile)) -and
        (Test-Path $TokensFile) -and (Test-Path $VoicesFile) -and
        (Test-Path $ChineseLexicon) -and (Test-Path $EspeakData) -and
        (Test-Path $LicenseFile)
}

Write-Host "Installing offline speech runtime packages..." -ForegroundColor Cyan
& $PythonExe -m pip install -e "$ProjectRoot[voice]"
if ($LASTEXITCODE -ne 0) {
    throw "Speech package installation failed."
}

if (-not [string]::IsNullOrWhiteSpace($env:JARVIS_DATA_DIR)) {
    $DataRoot = [System.IO.Path]::GetFullPath($env:JARVIS_DATA_DIR)
} else {
    $DataRoot = Join-Path $env:LOCALAPPDATA "JarvisAssistant"
}
$TtsRoot = Join-Path $DataRoot "models\tts"
$ModelDirectory = Join-Path $TtsRoot $ModelFolder

if (Test-KokoroModel $ModelDirectory) {
    Write-Host "The Kokoro multi-voice Chinese/English model is already installed: $ModelDirectory" -ForegroundColor Green
} elseif (Test-Path $ModelDirectory) {
    throw "An incomplete model directory exists at $ModelDirectory. Rename it before retrying; the installer will not overwrite it."
} elseif (Confirm-Download "Download the roughly 334 MiB Kokoro multi-voice Chinese/English model from the official k2-fsa/sherpa-onnx release") {
    New-Item -ItemType Directory -Force -Path $TtsRoot | Out-Null
    $StagingDirectory = Join-Path $TtsRoot (".jarvis-voice-install-" + $PID)
    $ArchivePath = Join-Path $StagingDirectory "$ModelFolder.tar.bz2"
    $ExtractedDirectory = Join-Path $StagingDirectory $ModelFolder
    try {
        New-Item -ItemType Directory -Path $StagingDirectory | Out-Null
        Write-Host "Downloading the Kokoro multi-voice model..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $ModelArchiveUrl -OutFile $ArchivePath
        Write-Host "Extracting and validating the model..." -ForegroundColor Cyan
        & tar.exe -xjf $ArchivePath -C $StagingDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "The model archive could not be extracted."
        }
        if (-not (Test-KokoroModel $ExtractedDirectory)) {
            throw "The download is missing model.onnx, voices.bin, tokens.txt, Chinese lexicon, espeak data, or LICENSE. Installation was refused."
        }
        Move-Item -Path $ExtractedDirectory -Destination $ModelDirectory
        Write-Host "The Kokoro model is ready. Default voice: zf_xiaoxiao (speaker 47)." -ForegroundColor Green
    } finally {
        if (Test-Path $StagingDirectory) {
            Remove-Item -LiteralPath $StagingDirectory -Recurse -Force
        }
    }
} else {
    Write-Host "Kokoro model download skipped. System speech fallback remains available." -ForegroundColor Yellow
}

if (Confirm-Download "Pre-download the roughly 500 MB faster-whisper small recognition model") {
    Write-Host "Preloading the faster-whisper model..." -ForegroundColor Cyan
    & $PythonExe (Join-Path $PSScriptRoot "preload_whisper.py") --model small
    if ($LASTEXITCODE -ne 0) {
        throw "The faster-whisper model download failed."
    }
} else {
    Write-Host "Recognition model download skipped. faster-whisper will obtain it when first used." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "JARVIS LOCAL offline speech setup is complete." -ForegroundColor Green
Write-Host "Model directory: $ModelDirectory"
Write-Host "Use Settings > Speech Synthesis in the app to test the voice."
