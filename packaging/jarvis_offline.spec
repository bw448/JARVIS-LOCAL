import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


PROJECT_ROOT = Path(SPECPATH).resolve().parent
DEBUG_CONSOLE = os.environ.get("JARVIS_BUILD_DEBUG_CONSOLE") == "1"
EXE_NAME = "JARVIS LOCAL Debug" if DEBUG_CONSOLE else "JARVIS LOCAL"
COLLECT_NAME = "JARVIS-LOCAL-DEBUG" if DEBUG_CONSOLE else "JARVIS-LOCAL"
ASSET_ROOT = PROJECT_ROOT / ".build-windows" / "assets"
TTS_MODEL = ASSET_ROOT / "models" / "tts" / "kokoro-multi-lang-v1_0"
STT_MODEL = ASSET_ROOT / "models" / "stt" / "faster-whisper-small"
ICON = ASSET_ROOT / "jarvis.ico"

for required in (TTS_MODEL, STT_MODEL, ICON):
    if not required.exists():
        raise SystemExit(f"Missing offline build asset: {required}")

datas = [
    (str(PROJECT_ROOT / "jarvis" / "static"), "jarvis/static"),
    (str(TTS_MODEL), "models/tts/kokoro-multi-lang-v1_0"),
    (str(STT_MODEL), "models/stt/faster-whisper-small"),
]
binaries = []
hiddenimports = [
    "keyring.backends.Windows",
    "tkinter",
    "PIL.Image",
    "PIL.ImageTk",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
]

for package in (
    "av",
    "clr_loader",
    "ctranslate2",
    "faster_whisper",
    "huggingface_hub",
    "keyring",
    "numpy",
    "PIL",
    "pythonnet",
    "sherpa_onnx",
    "tokenizers",
    "webview",
):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(PROJECT_ROOT / "desktop.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "cefpython3",
        "kokoro",
        "tensorflow",
        "torch",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=DEBUG_CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=str(PROJECT_ROOT / "packaging" / "windows_version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=COLLECT_NAME,
)
