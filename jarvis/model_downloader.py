"""
JARVIS 模型下载器

首次运行时自动下载语音模型，避免 GitHub 仓库过大。
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Optional

from .config import default_data_dir


# 模型配置
MODELS = {
    "tts_kokoro": {
        "name": "Kokoro TTS 语音合成模型",
        "size": "383MB",
        "target": "models/tts/kokoro-multi-lang-v1_0",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-multi-lang-v1_0.zip",
        "zip_name": "kokoro-multi-lang-v1_0.zip",
    },
    "stt_whisper": {
        "name": "Faster Whisper 语音识别模型",
        "size": "464MB",
        "target": "models/stt/faster-whisper-small",
        "url": "https://huggingface.co/systran/faster-whisper-small/resolve/main/model.bin",
        "files": {
            "model.bin": "https://huggingface.co/systran/faster-whisper-small/resolve/main/model.bin",
            "config.json": "https://huggingface.co/systran/faster-whisper-small/resolve/main/config.json",
            "tokenizer.json": "https://huggingface.co/systran/faster-whisper-small/resolve/main/tokenizer.json",
            "vocabulary.txt": "https://huggingface.co/systran/faster-whisper-small/resolve/main/vocabulary.txt",
        }
    }
}


def get_model_dir() -> Path:
    """获取模型存储目录"""
    if getattr(sys, 'frozen', False):
        # 打包后的 exe
        return Path(sys._MEIPASS) / "models"
    else:
        # 开发环境
        data_dir = default_data_dir()
        return data_dir / "models"


def check_models() -> dict[str, bool]:
    """检查模型是否存在"""
    model_dir = get_model_dir()
    result = {}
    
    for key, config in MODELS.items():
        target = model_dir / config["target"]
        result[key] = target.exists() and any(target.iterdir())
    
    return result


def download_with_progress(url: str, dest: Path, desc: str = "") -> bool:
    """带进度的下载"""
    try:
        print(f"  下载 {desc}...")
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        print(f"  下载失败: {e}")
        return False


def download_model(model_key: str) -> bool:
    """下载指定模型"""
    if model_key not in MODELS:
        print(f"未知模型: {model_key}")
        return False
    
    config = MODELS[model_key]
    model_dir = get_model_dir()
    target_dir = model_dir / config["target"]
    target_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"准备下载 {config['name']} ({config['size']})")
    
    # 如果是多文件模型
    if "files" in config:
        for filename, url in config["files"].items():
            dest = target_dir / filename
            if dest.exists():
                print(f"  {filename} 已存在，跳过")
                continue
            if not download_with_progress(url, dest, filename):
                return False
    else:
        # 单文件 zip
        zip_path = model_dir / config.get("zip_name", "model.zip")
        if not download_with_progress(config["url"], zip_path, config["name"]):
            return False
        
        # 解压
        print("  解压中...")
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(model_dir)
        zip_path.unlink()
    
    print(f"✓ {config['name']} 下载完成")
    return True


def ensure_models() -> bool:
    """确保所有模型都存在，缺失则下载"""
    status = check_models()
    all_ok = all(status.values())
    
    if all_ok:
        return True
    
    print("=" * 50)
    print("首次运行需要下载语音模型")
    print("=" * 50)
    
    for key, exists in status.items():
        if not exists:
            config = MODELS[key]
            print(f"\n需要下载: {config['name']} ({config['size']})")
            choice = input("下载？(y/n): ").strip().lower()
            
            if choice == 'y':
                if not download_model(key):
                    return False
            else:
                print(f"跳过 {config['name']}，语音功能将不可用")
    
    return True


if __name__ == "__main__":
    print("检查模型状态...\n")
    status = check_models()
    for key, exists in status.items():
        config = MODELS[key]
        icon = "✓" if exists else "✗"
        print(f"  {icon} {config['name']}: {'已存在' if exists else '缺失'}")
    
    if not all(status.values()):
        print("\n是否下载缺失模型？")
        ensure_models()
