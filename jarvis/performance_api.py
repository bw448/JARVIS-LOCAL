"""
性能监控API
提供性能统计和缓存管理接口
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from .speech_optimizer import get_tts_cache, get_metrics


def handle_performance_request(handler, path: str):
    """处理性能相关请求"""
    
    if path == "/api/performance":
        stats = {
            "tts_cache": get_tts_cache().stats(),
            "metrics": get_metrics().get_stats(),
        }
        handler._send_json(stats)
        return True
    
    if path == "/api/performance/clear-cache":
        get_tts_cache().clear()
        handler._send_json({"message": "缓存已清空"})
        return True
    
    return False


def add_performance_headers(handler):
    """添加性能相关的响应头"""
    # 添加缓存控制头
    handler.send_header("X-Cache-Hits", str(get_tts_cache().stats().get("hits", 0)))
    handler.send_header("X-Cache-Miss", str(get_tts_cache().stats().get("misses", 0)))
