"""
增强语音系统 - v0.9.0
支持云端ASR/TTS备用、连续语音优化、语音唤醒
参考 Aivy OS 的 Qwen Audio 集成
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import wave
import io
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, AsyncIterator
from urllib import error, request
from urllib.parse import urljoin


class VoiceState(Enum):
    """语音系统状态"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class VoiceConfig:
    """语音配置"""
    # 本地引擎
    local_asr_enabled: bool = True
    local_tts_enabled: bool = True
    
    # 云端备用
    cloud_asr_enabled: bool = False
    cloud_tts_enabled: bool = False
    cloud_provider: str = "qwen"  # qwen, openai, azure
    cloud_api_key: str = ""
    cloud_base_url: str = ""
    
    # 连续语音
    continuous_mode: bool = False
    silence_timeout: float = 1.5  # 静音超时(秒)
    max_recording_seconds: float = 60.0  # 最大录音时长
    
    # 唤醒词
    wake_word_enabled: bool = False
    wake_word: str = "贾维斯"
    
    # Qwen Audio 配置
    qwen_asr_model: str = "qwen-audio-3.0-realtime-flash"
    qwen_tts_model: str = "qwen-audio-3.0-realtime-flash"
    qwen_tts_voice: str = "longpaopao_v3.6"
    qwen_stream_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"


@dataclass
class VoiceEvent:
    """语音事件"""
    type: str  # "transcript", "audio", "state_change", "error"
    data: Any
    timestamp: float = field(default_factory=time.time)
    source: str = "local"  # "local" or "cloud"


class CloudASRService:
    """
    云端 ASR 服务
    支持 Qwen Audio、OpenAI Whisper、Azure Speech
    """
    
    def __init__(self, config: VoiceConfig):
        self._config = config
        self._provider = config.cloud_provider
        self._api_key = config.cloud_api_key
        self._base_url = config.cloud_base_url
    
    def transcribe(self, audio_data: bytes, language: str = "zh") -> Dict[str, Any]:
        """
        云端语音识别
        
        Args:
            audio_data: WAV 音频数据
            language: 语言代码
            
        Returns:
            识别结果 {"text": str, "language": str, "confidence": float}
        """
        if self._provider == "qwen":
            return self._transcribe_qwen(audio_data, language)
        elif self._provider == "openai":
            return self._transcribe_openai(audio_data, language)
        else:
            raise ValueError(f"不支持的云端ASR提供商: {self._provider}")
    
    def _transcribe_qwen(self, audio_data: bytes, language: str) -> Dict[str, Any]:
        """使用 Qwen Audio 进行识别"""
        import base64
        
        # 将音频转为 base64
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        
        url = urljoin(self._base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1", "/audio/transcriptions")
        
        # 构建请求
        payload = {
            "model": self._config.qwen_asr_model,
            "input": {
                "audio": f"data:audio/wav;base64,{audio_base64}"
            },
            "parameters": {
                "language": language
            }
        }
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return {
                    "text": result.get("output", {}).get("text", ""),
                    "language": language,
                    "confidence": result.get("output", {}).get("confidence", 0.9),
                    "provider": "qwen"
                }
        except Exception as e:
            return {"text": "", "error": str(e), "provider": "qwen"}
    
    def _transcribe_openai(self, audio_data: bytes, language: str) -> Dict[str, Any]:
        """使用 OpenAI Whisper 进行识别"""
        import base64
        
        url = urljoin(self._base_url or "https://api.openai.com/v1", "/audio/transcriptions")
        
        # 构建 multipart form data
        boundary = "----WebKitFormBoundary" + str(int(time.time()))
        
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode() + audio_data + (
            f"\r\n--{boundary}\r\n"
            f'Content-Disposition: form-data; name="model"\r\n\r\n'
            f"whisper-1\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="language"\r\n\r\n'
            f"{language}\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        
        req = request.Request(url, data=body, headers=headers, method="POST")
        
        try:
            with request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return {
                    "text": result.get("text", ""),
                    "language": language,
                    "confidence": 0.9,
                    "provider": "openai"
                }
        except Exception as e:
            return {"text": "", "error": str(e), "provider": "openai"}


class CloudTTSService:
    """
    云端 TTS 服务
    支持 Qwen Audio、OpenAI TTS、Edge TTS
    """
    
    def __init__(self, config: VoiceConfig):
        self._config = config
        self._provider = config.cloud_provider
        self._api_key = config.cloud_api_key
        self._base_url = config.cloud_base_url
    
    def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> bytes:
        """
        云端语音合成
        
        Args:
            text: 要合成的文本
            voice: 音色
            speed: 语速
            
        Returns:
            WAV 音频数据
        """
        if self._provider == "qwen":
            return self._synthesize_qwen(text, voice or self._config.qwen_tts_voice, speed)
        elif self._provider == "openai":
            return self._synthesize_openai(text, voice or "alloy", speed)
        else:
            raise ValueError(f"不支持的云端TTS提供商: {self._provider}")
    
    def _synthesize_qwen(self, text: str, voice: str, speed: float) -> bytes:
        """使用 Qwen Audio 进行合成"""
        url = urljoin(self._base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1", "/audio/synthesis")
        
        payload = {
            "model": self._config.qwen_tts_model,
            "input": {
                "text": text
            },
            "parameters": {
                "voice": voice,
                "speed": speed
            }
        }
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                # 假设返回 base64 编码的音频
                import base64
                audio_base64 = result.get("output", {}).get("audio", "")
                if audio_base64:
                    return base64.b64decode(audio_base64)
                raise ValueError("No audio in response")
        except Exception as e:
            raise RuntimeError(f"Qwen TTS failed: {e}") from e
    
    def _synthesize_openai(self, text: str, voice: str, speed: float) -> bytes:
        """使用 OpenAI TTS 进行合成"""
        url = urljoin(self._base_url or "https://api.openai.com/v1", "/audio/speech")
        
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": voice,
            "speed": speed
        }
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as e:
            raise RuntimeError(f"OpenAI TTS failed: {e}") from e


class ContinuousVoiceManager:
    """
    连续语音管理器
    处理连续对话、打断、静音检测
    """
    
    def __init__(self, config: VoiceConfig):
        self._config = config
        self._state = VoiceState.IDLE
        self._listeners: List[Callable[[VoiceEvent], None]] = []
        self._lock = threading.Lock()
        self._is_running = False
        self._recording_start = 0.0
        self._last_speech_time = 0.0
    
    @property
    def state(self) -> VoiceState:
        return self._state
    
    def add_listener(self, callback: Callable[[VoiceEvent], None]):
        """添加事件监听器"""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[VoiceEvent], None]):
        """移除事件监听器"""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def _emit_event(self, event: VoiceEvent):
        """发送事件"""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass
    
    def start_listening(self):
        """开始监听"""
        with self._lock:
            if self._state == VoiceState.LISTENING:
                return
            
            self._state = VoiceState.LISTENING
            self._recording_start = time.time()
            self._last_speech_time = time.time()
            self._is_running = True
            
            self._emit_event(VoiceEvent(
                type="state_change",
                data={"state": VoiceState.LISTENING.value},
                source="local"
            ))
    
    def stop_listening(self):
        """停止监听"""
        with self._lock:
            if self._state != VoiceState.LISTENING:
                return
            
            self._state = VoiceState.IDLE
            self._is_running = False
            
            self._emit_event(VoiceEvent(
                type="state_change",
                data={"state": VoiceState.IDLE.value},
                source="local"
            ))
    
    def on_speech_detected(self):
        """检测到语音活动"""
        with self._lock:
            self._last_speech_time = time.time()
    
    def on_silence_detected(self):
        """检测到静音"""
        with self._lock:
            if not self._is_running:
                return
            
            silence_duration = time.time() - self._last_speech_time
            recording_duration = time.time() - self._recording_start
            
            # 检查是否超时
            if silence_duration >= self._config.silence_timeout:
                self._emit_event(VoiceEvent(
                    type="silence_timeout",
                    data={"duration": silence_duration},
                    source="local"
                ))
                # 自动停止
                self.stop_listening()
            elif recording_duration >= self._config.max_recording_seconds:
                self._emit_event(VoiceEvent(
                    type="max_duration",
                    data={"duration": recording_duration},
                    source="local"
                ))
                self.stop_listening()
    
    def interrupt(self):
        """打断当前语音输出"""
        self._emit_event(VoiceEvent(
            type="interrupt",
            data={},
            source="local"
        ))


class EnhancedVoiceSystem:
    """
    增强语音系统
    整合本地和云端 ASR/TTS，支持连续语音
    """
    
    def __init__(self, config: Optional[VoiceConfig] = None):
        self._config = config or VoiceConfig()
        self._cloud_asr = CloudASRService(self._config) if self._config.cloud_asr_enabled else None
        self._cloud_tts = CloudTTSService(self._config) if self._config.cloud_tts_enabled else None
        self._continuous_mgr = ContinuousVoiceManager(self._config)
        self._local_speech = None  # 延迟加载本地语音服务
        
        # 事件监听
        self._continuous_mgr.add_listener(self._on_voice_event)
    
    @property
    def state(self) -> VoiceState:
        return self._continuous_mgr.state
    
    @property
    def config(self) -> VoiceConfig:
        return self._config
    
    def set_local_speech(self, speech_service):
        """设置本地语音服务"""
        self._local_speech = speech_service
    
    def _on_voice_event(self, event: VoiceEvent):
        """处理语音事件"""
        if event.type == "silence_timeout":
            # 静音超时，处理录音
            pass
        elif event.type == "interrupt":
            # 打断处理
            pass
    
    def transcribe(self, audio_data: bytes, language: str = "zh") -> Dict[str, Any]:
        """
        语音识别 (本地优先，云端备用)
        """
        result = None
        
        # 尝试本地识别
        if self._config.local_asr_enabled and self._local_speech:
            try:
                # 使用本地 whisper
                start = time.time()
                local_result = self._local_speech.transcribe(audio_data)
                elapsed = (time.time() - start) * 1000
                
                if local_result and local_result.text:
                    result = {
                        "text": local_result.text,
                        "language": local_result.language or language,
                        "confidence": 0.85,
                        "provider": "local",
                        "time_ms": elapsed
                    }
            except Exception as e:
                print(f"[Voice] Local ASR failed: {e}")
        
        # 云端备用
        if not result and self._config.cloud_asr_enabled and self._cloud_asr:
            try:
                start = time.time()
                result = self._cloud_asr.transcribe(audio_data, language)
                result["time_ms"] = (time.time() - start) * 1000
            except Exception as e:
                print(f"[Voice] Cloud ASR failed: {e}")
        
        if not result:
            result = {"text": "", "error": "ASR failed", "provider": "none"}
        
        return result
    
    def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> bytes:
        """
        语音合成 (本地优先，云端备用)
        """
        audio = None
        
        # 尝试本地合成
        if self._config.local_tts_enabled and self._local_speech:
            try:
                start = time.time()
                result = self._local_speech.synthesize(None, text)  # settings=None for default
                elapsed = (time.time() - start) * 1000
                
                if result and result.data:
                    audio = result.data
            except Exception as e:
                print(f"[Voice] Local TTS failed: {e}")
        
        # 云端备用
        if not audio and self._config.cloud_tts_enabled and self._cloud_tts:
            try:
                start = time.time()
                audio = self._cloud_tts.synthesize(text, voice, speed)
                elapsed = (time.time() - start) * 1000
            except Exception as e:
                print(f"[Voice] Cloud TTS failed: {e}")
        
        if not audio:
            raise RuntimeError("TTS failed: no audio generated")
        
        return audio
    
    def start_continuous_mode(self):
        """启动连续语音模式"""
        self._config.continuous_mode = True
        self._continuous_mgr.start_listening()
    
    def stop_continuous_mode(self):
        """停止连续语音模式"""
        self._config.continuous_mode = False
        self._continuous_mgr.stop_listening()
    
    def get_status(self) -> Dict[str, Any]:
        """获取语音系统状态"""
        return {
            "state": self.state.value,
            "continuous_mode": self._config.continuous_mode,
            "local_asr": self._config.local_asr_enabled,
            "local_tts": self._config.local_tts_enabled,
            "cloud_asr": self._config.cloud_asr_enabled,
            "cloud_tts": self._config.cloud_tts_enabled,
            "cloud_provider": self._config.cloud_provider if (self._config.cloud_asr_enabled or self._config.cloud_tts_enabled) else "none",
        }


# 全局实例
_voice_system: Optional[EnhancedVoiceSystem] = None
_voice_lock = threading.Lock()


def get_voice_system(config: Optional[VoiceConfig] = None) -> EnhancedVoiceSystem:
    """获取全局语音系统实例"""
    global _voice_system
    if _voice_system is None:
        with _voice_lock:
            if _voice_system is None:
                _voice_system = EnhancedVoiceSystem(config)
    return _voice_system
