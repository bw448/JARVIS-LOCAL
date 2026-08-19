"""
语音服务优化模块
提供TTS缓存、预热优化、内存管理等功能
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .config import Settings, default_data_dir


class TTSCache:
    """TTS音频缓存管理器，缓存常用短语的合成结果"""
    
    def __init__(self, max_size_mb: int = 100, max_entries: int = 1000):
        self._cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._max_entries = max_entries
        self._current_size = 0
        self._hits = 0
        self._misses = 0
    
    def _make_key(self, text: str, voice: str, speed: float) -> str:
        """生成缓存键"""
        content = f"{text}|{voice}|{speed:.2f}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def get(self, text: str, voice: str, speed: float) -> tuple[bytes, str] | None:
        """获取缓存的音频"""
        key = self._make_key(text, voice, speed)
        with self._lock:
            if key in self._cache:
                self._hits += 1
                # 移到最近使用
                self._cache.move_to_end(key)
                return self._cache[key]
            self._misses += 1
            return None
    
    def put(self, text: str, voice: str, speed: float, audio: bytes, content_type: str):
        """缓存音频结果"""
        key = self._make_key(text, voice, speed)
        audio_size = len(audio)
        
        with self._lock:
            # 如果已存在，更新大小
            if key in self._cache:
                old_audio, _ = self._cache[key]
                self._current_size -= len(old_audio)
            else:
                # 检查是否需要清理
                while (len(self._cache) >= self._max_entries or 
                       self._current_size + audio_size > self._max_size_bytes):
                    if not self._cache:
                        break
                    # 移除最久未使用的
                    _, (old_audio, _) = self._cache.popitem(last=False)
                    self._current_size -= len(old_audio)
            
            self._cache[key] = (audio, content_type)
            self._current_size += audio_size
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._current_size = 0
            self._hits = 0
            self._misses = 0
    
    def stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._cache),
                "size_mb": self._current_size / (1024 * 1024),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0,
            }


class SpeechMetrics:
    """语音服务性能指标收集"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._tts_times: list[float] = []
        self._stt_times: list[float] = []
    
    def record_tts_time(self, duration_ms: float):
        """记录TTS耗时"""
        with self._lock:
            self._tts_times.append(duration_ms)
            # 只保留最近100条记录
            if len(self._tts_times) > 100:
                self._tts_times = self._tts_times[-100:]
    
    def record_stt_time(self, duration_ms: float):
        """记录STT耗时"""
        with self._lock:
            self._stt_times.append(duration_ms)
            if len(self._stt_times) > 100:
                self._stt_times = self._stt_times[-100:]
    
    def get_stats(self) -> dict[str, Any]:
        """获取性能统计"""
        with self._lock:
            tts_avg = sum(self._tts_times) / len(self._tts_times) if self._tts_times else 0
            stt_avg = sum(self._stt_times) / len(self._stt_times) if self._stt_times else 0
            
            return {
                "tts": {
                    "avg_ms": round(tts_avg, 2),
                    "samples": len(self._tts_times),
                },
                "stt": {
                    "avg_ms": round(stt_avg, 2),
                    "samples": len(self._stt_times),
                },
            }


# 全局实例
_tts_cache = TTSCache()
_metrics = SpeechMetrics()


def get_tts_cache() -> TTSCache:
    """获取TTS缓存实例"""
    return _tts_cache


def get_metrics() -> SpeechMetrics:
    """获取性能指标实例"""
    return _metrics
