"""
语音服务补丁 - 添加TTS缓存功能
"""

import time
from typing import Any

from .speech_optimizer import get_tts_cache, get_metrics


def patch_speech_service(speech_service):
    """给SpeechService添加缓存功能"""
    
    original_synthesize = speech_service.synthesize
    
    def synthesize_with_cache(settings, text):
        """带缓存的合成方法"""
        cleaned = str(text or "").strip()
        if not cleaned:
            from .speech import SpeechError
            raise SpeechError("没有可朗读的文字")
        
        if len(cleaned) > 4000:
            from .speech import SpeechError
            raise SpeechError("单次朗读不能超过 4000 个字符")
        
        if settings.tts.provider == "system":
            return None
        
        # 检查缓存
        cache = get_tts_cache()
        cached = cache.get(cleaned, settings.tts.voice, settings.tts.speed)
        if cached:
            get_metrics().record_cache_hit()
            from .speech import AudioResult
            return AudioResult(cached[0], cached[1])
        
        get_metrics().record_cache_miss()
        
        # 正常合成
        start_time = time.time()
        result = original_synthesize(settings, text)
        duration_ms = (time.time() - start_time) * 1000
        
        # 缓存结果
        if result is not None:
            cache.put(cleaned, settings.tts.voice, settings.tts.speed, 
                     result.data, result.content_type)
            get_metrics().record_tts_time(duration_ms)
        
        return result
    
    # 替换方法
    speech_service.synthesize = synthesize_with_cache
    
    return speech_service


def get_performance_stats():
    """获取性能统计"""
    return {
        'tts_cache': get_tts_cache().stats(),
        'metrics': get_metrics().get_stats(),
    }
