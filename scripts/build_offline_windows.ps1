param(
    [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
$global:LASTEXITCODE = 0

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildRoot = Join-Path $ProjectRoot ".build-windows"
$DownloadRoot = Join-Path $BuildRoot "downloads"
$PythonVersion = "3.11.9"
$PythonRoot = Join-Path $BuildRoot "python-$PythonVersion"
$PythonExe = Join-Path $PythonRoot "python.exe"
$AssetRoot = Join-Path $BuildRoot "assets"
$ModelRoot = Join-Path $AssetRoot "models"
$TtsRoot = Join-Path $ModelRoot "tts"
$TtsModel = Join-Path $TtsRoot "kokoro-multi-lang-v1_0"
$SttModel = Join-Path $ModelRoot "stt\faster-whisper-small"
$PrerequisiteRoot = Join-Path $AssetRoot "prerequisites"
$DistRoot = Join-Path $ProjectRoot "dist"
$ReleaseName = "JARVIS-LOCAL-0.7.1-Windows-x64-Offline"
$ReleaseDirectory = Join-Path $DistRoot $ReleaseName
$ArchivePath = Join-Path $DistRoot "$ReleaseName.zip"

$PythonInstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$KokoroUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2"
$WebView2Url = "https://go.microsoft.com/fwlink/?linkid=2124701"

function ConvertTo-NativeArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $ArgumentString = (($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join " ")
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $ArgumentString
    $StartInfo.WorkingDirectory = $ProjectRoot
    $StartInfo.UseShellExecute = $false
    $Process = [System.Diagnostics.Process]::Start($StartInfo)
    $Process.WaitForExit()
    return $Process.ExitCode
}

function Invoke-NativeCapture {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $ArgumentString = (($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join " ")
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $ArgumentString
    $StartInfo.WorkingDirectory = $ProjectRoot
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $Process = [System.Diagnostics.Process]::Start($StartInfo)
    $Output = $Process.StandardOutput.ReadToEnd()
    $ErrorOutput = $Process.StandardError.ReadToEnd()
    $Process.WaitForExit()
    if ($Process.ExitCode -ne 0) {
        throw "Command failed: $FilePath $ErrorOutput"
    }
    return $Output
}

function Invoke-Download {
    param([string]$Uri, [string]$Destination)
    $Parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    if (Test-Path $Destination) {
        return
    }
    Write-Host "Downloading $Uri" -ForegroundColor Cyan
    $ExitCode = Invoke-NativeCommand "curl.exe" @(
        "-L", "--fail", "--retry", "3", "--ssl-revoke-best-effort",
        "--output", $Destination, $Uri
    )
    if ($ExitCode -ne 0) {
        throw "Download failed: $Uri"
    }
}

function Assert-SignedBy {
    param([string]$Path, [string]$Publisher)
    $Signature = Get-AuthenticodeSignature -FilePath $Path
    if ($Signature.Status -ne "Valid" -or $Signature.SignerCertificate.Subject -notlike "*$Publisher*") {
        throw "Signature verification failed for $Path"
    }
}

function Test-KokoroModel {
    param([string]$Path)
    return (Test-Path (Join-Path $Path "model.onnx")) -and
        (Test-Path (Join-Path $Path "voices.bin")) -and
        (Test-Path (Join-Path $Path "tokens.txt")) -and
        (Test-Path (Join-Path $Path "lexicon-us-en.txt")) -and
        (Test-Path (Join-Path $Path "lexicon-zh.txt")) -and
        (Test-Path (Join-Path $Path "espeak-ng-data")) -and
        (Test-Path (Join-Path $Path "LICENSE"))
}

New-Item -ItemType Directory -Force -Path $BuildRoot, $DownloadRoot, $AssetRoot, $DistRoot | Out-Null

if (-not (Test-Path $PythonExe)) {
    $PythonInstaller = Join-Path $DownloadRoot "python-$PythonVersion-amd64.exe"
    Invoke-Download $PythonInstallerUrl $PythonInstaller
    Assert-SignedBy $PythonInstaller "Python Software Foundation"
    Write-Host "Installing the project-local Python build runtime..." -ForegroundColor Cyan
    $PythonInstallExitCode = Invoke-NativeCommand $PythonInstaller @(
        "/quiet", "InstallAllUsers=0", "TargetDir=$PythonRoot", "Include_doc=0",
        "Include_debug=0", "Include_dev=0", "Include_launcher=0", "Include_pip=1",
        "Include_test=0", "Include_tools=0", "Shortcuts=0", "AssociateFiles=0",
        "PrependPath=0"
    )
    if ($PythonInstallExitCode -notin @(0, 1641, 3010) -or -not (Test-Path $PythonExe)) {
        throw "Project-local Python installation failed."
    }
}

Write-Host "Installing pinned build and runtime dependencies..." -ForegroundColor Cyan
$ExitCode = Invoke-NativeCommand $PythonExe @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
if ($ExitCode -ne 0) { throw "pip bootstrap failed." }
$ProjectExtras = "${ProjectRoot}[voice,desktop]"
$ExitCode = Invoke-NativeCommand $PythonExe @("-m", "pip", "install", "-e", $ProjectExtras, "pyinstaller>=6.21,<7", "pillow>=11,<13")
if ($ExitCode -ne 0) { throw "Dependency installation failed." }

$KokoroArchive = Join-Path $DownloadRoot "kokoro-multi-lang-v1_0.tar.bz2"
if (-not (Test-KokoroModel $TtsModel)) {
    if (Test-Path $TtsModel) {
        throw "Incomplete Kokoro asset directory: $TtsModel"
    }
    Invoke-Download $KokoroUrl $KokoroArchive
    $TtsStage = Join-Path $BuildRoot "tts-stage"
    if (Test-Path $TtsStage) { Remove-Item -LiteralPath $TtsStage -Recurse -Force }
    New-Item -ItemType Directory -Path $TtsStage | Out-Null
    $ExitCode = Invoke-NativeCommand "tar.exe" @("-xjf", $KokoroArchive, "-C", $TtsStage)
    if ($ExitCode -ne 0) { throw "Kokoro extraction failed." }
    $Extracted = Join-Path $TtsStage "kokoro-multi-lang-v1_0"
    if (-not (Test-KokoroModel $Extracted)) { throw "Kokoro archive validation failed." }
    New-Item -ItemType Directory -Force -Path $TtsRoot | Out-Null
    Move-Item -Path $Extracted -Destination $TtsModel
    Remove-Item -LiteralPath $TtsStage -Recurse -Force
}

Write-Host "Preparing the pinned faster-whisper small model..." -ForegroundColor Cyan
$ExitCode = Invoke-NativeCommand $PythonExe @(
    (Join-Path $PSScriptRoot "prepare_offline_assets.py"),
    "--whisper-dir", $SttModel,
    "--manifest", (Join-Path $AssetRoot "whisper-manifest.json")
)
if ($ExitCode -ne 0) { throw "Whisper asset preparation failed." }

$WebViewInstaller = Join-Path $PrerequisiteRoot "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
Invoke-Download $WebView2Url $WebViewInstaller
Assert-SignedBy $WebViewInstaller "Microsoft Corporation"

$ExitCode = Invoke-NativeCommand $PythonExe @(
    (Join-Path $PSScriptRoot "create_windows_icon.py"),
    (Join-Path $AssetRoot "jarvis.ico"),
    "--source", (Join-Path $ProjectRoot "assets\jarvis-hud-logo.png")
)
if ($ExitCode -ne 0) { throw "Icon generation failed." }

$PyInstallerWork = Join-Path $BuildRoot "pyinstaller"
if (Test-Path $PyInstallerWork) { Remove-Item -LiteralPath $PyInstallerWork -Recurse -Force }
$RawDist = Join-Path $DistRoot "JARVIS-LOCAL"
if (Test-Path $RawDist) { Remove-Item -LiteralPath $RawDist -Recurse -Force }
if (Test-Path $ReleaseDirectory) { Remove-Item -LiteralPath $ReleaseDirectory -Recurse -Force }

Write-Host "Freezing JARVIS LOCAL and embedding both voice models..." -ForegroundColor Cyan
$ExitCode = Invoke-NativeCommand $PythonExe @(
    "-m", "PyInstaller", "--noconfirm", "--clean",
    "--workpath", $PyInstallerWork,
    "--distpath", $DistRoot,
    (Join-Path $ProjectRoot "packaging\jarvis_offline.spec")
)
if ($ExitCode -ne 0 -or -not (Test-Path $RawDist)) { throw "PyInstaller build failed." }
Move-Item -Path $RawDist -Destination $ReleaseDirectory

$ReleasePrerequisites = Join-Path $ReleaseDirectory "Prerequisites"
New-Item -ItemType Directory -Path $ReleasePrerequisites | Out-Null
Copy-Item $WebViewInstaller $ReleasePrerequisites
Copy-Item (Join-Path $ProjectRoot "packaging\INSTALL_WEBVIEW2.cmd") $ReleasePrerequisites
Copy-Item (Join-Path $ProjectRoot "packaging\README-OFFLINE.md") (Join-Path $ReleaseDirectory "README-OFFLINE.md")
Copy-Item (Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.md") $ReleaseDirectory
Copy-Item (Join-Path $ProjectRoot "ORIGINALITY.md") $ReleaseDirectory
Copy-Item (Join-Path $TtsModel "LICENSE") (Join-Path $ReleaseDirectory "KOKORO-MODEL-LICENSE.txt")
Copy-Item (Join-Path $ProjectRoot "packaging\WHISPER-MODEL-LICENSE.txt") (Join-Path $ReleaseDirectory "WHISPER-MODEL-LICENSE.txt")
Copy-Item (Join-Path $AssetRoot "whisper-manifest.json") (Join-Path $ReleaseDirectory "WHISPER-MODEL-MANIFEST.json")

$PackageList = Invoke-NativeCapture $PythonExe @("-m", "pip", "freeze")
$PackageLines = @(
    $PackageList -split "`r?`n" |
        Where-Object { $_ -and $_ -notmatch '^# Editable install' -and $_ -notmatch '^-e\s+' }
)
$PackageLines += "jarvis-assistant==0.7.1"
$SanitizedPackageList = ($PackageLines | Sort-Object -Unique) -join "`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $ReleaseDirectory "PYTHON-PACKAGES.txt"),
    $SanitizedPackageList + "`r`n",
    (New-Object System.Text.UTF8Encoding($false))
)
$PythonVersion = (Invoke-NativeCapture $PythonExe @("--version")).Trim()

$BuildInfo = [ordered]@{
    app = "JARVIS LOCAL"
    version = "0.7.1"
    edition = "Windows x64 complete offline voice"
    built_at = (Get-Date).ToUniversalTime().ToString("o")
    python = $PythonVersion
    kokoro_archive_sha256 = (Get-FileHash $KokoroArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    whisper_model_sha256 = (Get-FileHash (Join-Path $SttModel "model.bin") -Algorithm SHA256).Hash.ToLowerInvariant()
    webview2_installer_sha256 = (Get-FileHash $WebViewInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
}
$BuildInfo | ConvertTo-Json | Out-File -Encoding utf8 (Join-Path $ReleaseDirectory "BUILD-INFO.json")

$SelfTestReport = Join-Path $ReleaseDirectory "SELF-TEST.json"
$SelfTestArguments = "--self-test `"$SelfTestReport`""
$SelfTest = Start-Process -FilePath (Join-Path $ReleaseDirectory "JARVIS LOCAL.exe") -ArgumentList $SelfTestArguments -Wait -PassThru
if ($SelfTest.ExitCode -ne 0) {
    if (Test-Path $SelfTestReport) { Get-Content $SelfTestReport }
    throw "Frozen offline speech self-test failed."
}
$SelfTestData = Get-Content -LiteralPath $SelfTestReport -Raw -Encoding UTF8 | ConvertFrom-Json
$SelfTestData.bundle_root = "_internal"
$SelfTestData.stt_model = "_internal\models\stt\faster-whisper-small"
$SanitizedSelfTest = $SelfTestData | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText(
    $SelfTestReport,
    $SanitizedSelfTest + "`r`n",
    (New-Object System.Text.UTF8Encoding($false))
)

$AcceptanceReport = Join-Path $ReleaseDirectory "ACCEPTANCE-REPORT.md"
$ExitCode = Invoke-NativeCommand $PythonExe @(
    (Join-Path $PSScriptRoot "windows_acceptance.py"),
    "--package-dir", $ReleaseDirectory,
    "--output", $AcceptanceReport
)
if ($ExitCode -ne 0) {
    throw "Frozen offline package acceptance diagnostics failed."
}

if (-not $SkipArchive) {
    if (Test-Path $ArchivePath) { Remove-Item -LiteralPath $ArchivePath -Force }
    Write-Host "Creating the portable ZIP archive..." -ForegroundColor Cyan
    $ExitCode = Invoke-NativeCommand "tar.exe" @("-a", "-cf", $ArchivePath, "-C", $DistRoot, $ReleaseName)
    if ($ExitCode -ne 0) { throw "Archive creation failed." }
    $ArchiveHash = (Get-FileHash $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    "$ArchiveHash  $ReleaseName.zip" | Out-File -Encoding ascii (Join-Path $DistRoot "$ReleaseName.sha256")
}

$ReleaseBytes = (Get-ChildItem $ReleaseDirectory -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host "Offline release ready: $ReleaseDirectory" -ForegroundColor Green
Write-Host "Release size: $ReleaseBytes bytes"
if (-not $SkipArchive) { Write-Host "Archive: $ArchivePath" }
