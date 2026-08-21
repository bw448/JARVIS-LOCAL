"""
JARVIS 首次运行设置

自动下载缺失的语音模型，确保开箱即用。
"""

from __future__ import annotations

import os
import sys
import urllib.request
import zipfile
from pathlib import Path


def get_model_dir() -> Path:
    """获取模型目录"""
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        return exe_dir / "_internal" / "models"
    else:
        return Path(__file__).parent.parent / ".build-windows" / "assets" / "models"


def check_tts_model() -> bool:
    """检查 TTS 模型是否存在"""
    model_dir = get_model_dir()
    tts_dir = model_dir / "tts" / "kokoro-multi-lang-v1_0"
    return tts_dir.exists() and any(tts_dir.iterdir())


def check_stt_model() -> bool:
    """检查 STT 模型是否存在"""
    model_dir = get_model_dir()
    stt_dir = model_dir / "stt" / "faster-whisper-small"
    return stt_dir.exists() and (stt_dir / "model.bin").exists()


def download_file(url: str, dest: Path, desc: str = "") -> bool:
    """下载文件"""
    try:
        print(f"  下载 {desc}...")
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        print(f"  ✓ {desc} 下载完成")
        return True
    except Exception as e:
        print(f"  ✗ 下载失败: {e}")
        return False


def setup_first_run() -> bool:
    """首次运行设置"""
    print("=" * 50)
    print("JARVIS 首次运行设置")
    print("=" * 50)
    
    tts_ok = check_tts_model()
    stt_ok = check_stt_model()
    
    if tts_ok and stt_ok:
        print("\n✓ 所有模型已就绪")
        return True
    
    print("\n语音模型缺失，请从以下地址下载完整离线包：")
    print("https://github.com/你的用户名/JARVIS-LOCAL/releases")
    print("\n或手动放置模型到：")
    print(f"  {get_model_dir()}")
    
    return False


if __name__ == "__main__":
    setup_first_run()
