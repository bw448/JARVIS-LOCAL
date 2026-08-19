"""
应用集成模块
将ComputerUse和语音优化集成到主应用
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from .computer_use import ComputerUseService, ComputerUseError
from .speech_optimizer import get_tts_cache, get_metrics


class EnhancedJarvisApplication:
    """增强版贾维斯应用，集成Computer Use和语音优化"""
    
    def __init__(self, original_app):
        self._app = original_app
        self.computer = ComputerUseService()
        self._setup_speech_cache()
    
    def _setup_speech_cache(self):
        """设置语音缓存"""
        from .speech_patch import patch_speech_service
        self._app.speech = patch_speech_service(self._app.speech)
    
    @property
    def settings(self):
        return self._app.settings
    
    @property
    def speech(self):
        return self._app.speech
    
    @property
    def brain(self):
        return self._app.brain
    
    @property
    def secret_store(self):
        return self._app.secret_store
    
    def public_state(self) -> dict[str, Any]:
        """获取公开状态，包含Computer Use信息"""
        state = self._app.public_state()
        
        # 添加Computer Use信息
        state["computer_control"]["tools"] = [
            schema["function"]["name"] for schema in self.computer.schemas()
        ]
        
        # 添加性能统计
        from .speech_optimizer import get_tts_cache, get_metrics
        state["performance"] = {
            "tts_cache": get_tts_cache().stats(),
            "metrics": get_metrics().get_stats(),
        }
        
        return state
    
    def resolve_tool(self, payload: Any) -> dict[str, Any]:
        """解决工具调用"""
        if not isinstance(payload, Mapping):
            raise ComputerUseError("操作确认格式无效")
        
        if not self.settings.interaction.computer_control_enabled:
            raise ComputerUseError("电脑控制已经关闭")
        
        return self.computer.resolve(
            str(payload.get("proposal_id", "")),
            payload.get("approved") is True,
        )
    
    def get_performance_stats(self) -> dict[str, Any]:
        """获取性能统计"""
        return {
            "tts_cache": get_tts_cache().stats(),
            "metrics": get_metrics().get_stats(),
        }
    
    def clear_cache(self):
        """清空缓存"""
        get_tts_cache().clear()
    
    def __getattr__(self, name):
        """代理其他属性到原始应用"""
        return getattr(self._app, name)


def enhance_application(app):
    """增强应用实例"""
    return EnhancedJarvisApplication(app)
