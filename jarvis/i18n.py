"""
Internationalization (i18n) module for JARVIS Assistant.
Provides multi-language support for the UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

# Default translations
DEFAULT_TRANSLATIONS = {
    "zh-CN": {
        "system_standby": "系统待命",
        "listening": "正在聆听",
        "transcribing": "本地识别",
        "thinking": "正在思考",
        "speaking": "正在回应",
        "error": "需要处理",
        "click_to_start": "点击核心开始对话",
        "voice_running": "连续语音运行中",
        "enable_voice": "开启连续语音模式",
        "disable_voice": "关闭连续语音模式",
        "hide_assistant": "隐藏悬浮助手",
        "show_panel": "打开主面板",
        "expand_assistant": "展开悬浮助手",
        "assistant_expanded": "悬浮助手已展开",
        "theme_cyan": "青色主题",
        "theme_violet": "紫色主题",
        "theme_emerald": "翠绿主题",
        "theme_amber": "琥珀主题",
    },
    "en": {
        "system_standby": "System Standby",
        "listening": "Listening",
        "transcribing": "Transcribing",
        "thinking": "Thinking",
        "speaking": "Speaking",
        "error": "Error",
        "click_to_start": "Click core to start",
        "voice_running": "Continuous voice active",
        "enable_voice": "Enable continuous voice",
        "disable_voice": "Disable continuous voice",
        "hide_assistant": "Hide assistant",
        "show_panel": "Open main panel",
        "expand_assistant": "Expand assistant",
        "assistant_expanded": "Assistant expanded",
        "theme_cyan": "Cyan theme",
        "theme_violet": "Violet theme",
        "theme_emerald": "Emerald theme",
        "theme_amber": "Amber theme",
    },
    "ja": {
        "system_standby": "システム待機",
        "listening": "リスニング",
        "transcribing": "文字起こし",
        "thinking": "思考中",
        "speaking": "話中",
        "error": "エラー",
        "click_to_start": "コアをクリックして開始",
        "voice_running": "連続音声アクティブ",
        "enable_voice": "連続音声を有効にする",
        "disable_voice": "連続音声を無効にする",
        "hide_assistant": "アシスタントを隠す",
        "show_panel": "メインパネルを開く",
        "expand_assistant": "アシスタントを展開",
        "assistant_expanded": "アシスタント展開済み",
        "theme_cyan": "シアンテーマ",
        "theme_violet": "バイオレットテーマ",
        "theme_emerald": "エメラルドテーマ",
        "theme_amber": "アンバーテーマ",
    },
}

class I18n:
    """Internationalization manager."""
    
    def __init__(self, language: str = "zh-CN", translations_dir: Optional[Path] = None):
        self.language = language
        self.translations_dir = translations_dir
        self.translations: Dict[str, Dict[str, str]] = DEFAULT_TRANSLATIONS.copy()
        self._load_custom_translations()
    
    def _load_custom_translations(self):
        """Load custom translations from files."""
        if not self.translations_dir or not self.translations_dir.exists():
            return
        
        for lang_file in self.translations_dir.glob("*.json"):
            lang_code = lang_file.stem
            try:
                with open(lang_file, "r", encoding="utf-8") as f:
                    custom_translations = json.load(f)
                    if lang_code in self.translations:
                        self.translations[lang_code].update(custom_translations)
                    else:
                        self.translations[lang_code] = custom_translations
            except (json.JSONDecodeError, OSError):
                continue
    
    def t(self, key: str, **kwargs) -> str:
        """Translate a key to the current language."""
        lang_translations = self.translations.get(self.language, {})
        text = lang_translations.get(key, key)
        
        # Apply format kwargs if any
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError):
                pass
        
        return text
    
    def set_language(self, language: str):
        """Change the current language."""
        if language in self.translations:
            self.language = language
    
    def get_available_languages(self) -> list:
        """Get list of available languages."""
        return list(self.translations.keys())

# Global instance
_i18n: Optional[I18n] = None

def get_i18n() -> I18n:
    """Get the global i18n instance."""
    global _i18n
    if _i18n is None:
        _i18n = I18n()
    return _i18n

def t(key: str, **kwargs) -> str:
    """Translate a key using the global i18n instance."""
    return get_i18n().t(key, **kwargs)
