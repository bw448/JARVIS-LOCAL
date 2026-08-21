"""
WebSocket 实时语音流 - v1.0.0
支持双向流式语音通信
参考 Aivy OS 的 Qwen Audio 实时流
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import wave
import io
import base64
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, AsyncIterator, Set
from collections import deque


class StreamState(Enum):
    """流状态"""
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass
class AudioChunk:
    """音频数据块"""
    data: bytes
    timestamp: float
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2  # 16-bit


@dataclass
class TranscriptSegment:
    """识别结果片段"""
    text: str
    is_final: bool
    confidence: float = 0.0
    language: str = "zh"
    start_time: float = 0.0
    end_time: float = 0.0


@dataclass
class StreamEvent:
    """流事件"""
    type: str  # "transcript", "audio", "state", "error", "interrupt"
    data: Any
    timestamp: float = field(default_factory=time.time)


class AudioBuffer:
    """音频缓冲区"""
    
    def __init__(self, max_duration: float = 30.0, sample_rate: int = 16000):
        self._buffer: deque = deque()
        self._max_samples = int(max_duration * sample_rate)
        self._current_samples = 0
        self._lock = threading.Lock()
    
    def push(self, chunk: AudioChunk):
        """添加音频块"""
        with self._lock:
            samples = len(chunk.data) // 2  # 16-bit = 2 bytes per sample
            self._buffer.append(chunk)
            self._current_samples += samples
            
            # 超出最大长度时移除旧数据
            while self._current_samples > self._max_samples and self._buffer:
                old = self._buffer.popleft()
                self._current_samples -= len(old.data) // 2
    
    def get_all(self) -> bytes:
        """获取所有缓冲数据"""
        with self._lock:
            return b"".join(chunk.data for chunk in self._buffer)
    
    def get_recent(self, duration: float = 1.0, sample_rate: int = 16000) -> bytes:
        """获取最近N秒的数据"""
        target_samples = int(duration * sample_rate)
        with self._lock:
            result = bytearray()
            current = 0
            for chunk in reversed(self._buffer):
                result = chunk.data + result
                current += len(chunk.data) // 2
                if current >= target_samples:
                    break
            return bytes(result)
    
    def clear(self):
        """清空缓冲"""
        with self._lock:
            self._buffer.clear()
            self._current_samples = 0
    
    @property
    def duration(self) -> float:
        """当前缓冲时长(秒)"""
        return self._current_samples / 16000


class VoiceActivityDetector:
    """语音活动检测 (VAD)"""
    
    def __init__(
        self,
        energy_threshold: float = 0.01,
        silence_duration: float = 1.5,
        min_speech_duration: float = 0.3,
    ):
        self._energy_threshold = energy_threshold
        self._silence_duration = silence_duration
        self._min_speech_duration = min_speech_duration
        self._is_speaking = False
        self._speech_start = 0.0
        self._last_speech_time = 0.0
    
    @property
    def is_speaking(self) -> bool:
        return self._is_speaking
    
    def process_chunk(self, audio_data: bytes) -> Dict[str, Any]:
        """
        处理音频块，检测语音活动
        
        Returns:
            {"is_speech": bool, "is_start": bool, "is_end": bool, "energy": float}
        """
        # 计算能量
        import struct
        samples = struct.unpack(f"<{len(audio_data)//2}h", audio_data)
        if not samples:
            return {"is_speech": False, "is_start": False, "is_end": False, "energy": 0.0}
        
        # 归一化能量
        max_val = max(abs(s) for s in samples) if samples else 1
        energy = (sum(s*s for s in samples) / len(samples)) ** 0.5 / 32768.0
        
        now = time.time()
        is_speech = energy > self._energy_threshold
        
        result = {
            "is_speech": is_speech,
            "is_start": False,
            "is_end": False,
            "energy": energy,
        }
        
        if is_speech:
            if not self._is_speaking:
                # 语音开始
                self._is_speaking = True
                self._speech_start = now
                result["is_start"] = True
            self._last_speech_time = now
        elif self._is_speaking:
            # 检查是否静音超时
            if now - self._last_speech_time >= self._silence_duration:
                speech_duration = now - self._speech_start
                if speech_duration >= self._min_speech_duration:
                    self._is_speaking = False
                    result["is_end"] = True
        
        return result


class RealtimeVoiceStream:
    """
    实时语音流
    处理双向音频流、VAD、实时识别
    """
    
    def __init__(
        self,
        asr_callback: Optional[Callable[[bytes], TranscriptSegment]] = None,
        tts_callback: Optional[Callable[[str], AsyncIterator[bytes]]] = None,
    ):
        self._state = StreamState.IDLE
        self._asr_callback = asr_callback
        self._tts_callback = tts_callback
        
        self._audio_buffer = AudioBuffer(max_duration=60.0)
        self._vad = VoiceActivityDetector()
        
        self._listeners: List[Callable[[StreamEvent], None]] = []
        self._lock = threading.RLock()
        
        self._is_running = False
        self._process_thread: Optional[threading.Thread] = None
        
        # 统计
        self._chunks_received = 0
        self._segments_transcribed = 0
        self._start_time = 0.0
    
    @property
    def state(self) -> StreamState:
        return self._state
    
    def add_listener(self, callback: Callable[[StreamEvent], None]):
        """添加事件监听"""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[StreamEvent], None]):
        """移除事件监听"""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def _emit(self, event: StreamEvent):
        """发送事件"""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass
    
    def start(self):
        """启动流"""
        with self._lock:
            if self._is_running:
                return
            
            self._is_running = True
            self._state = StreamState.CONNECTED
            self._start_time = time.time()
            
            self._emit(StreamEvent(
                type="state",
                data={"state": StreamState.CONNECTED.value}
            ))
    
    def stop(self):
        """停止流"""
        with self._lock:
            self._is_running = False
            self._state = StreamState.IDLE
            
            self._emit(StreamEvent(
                type="state",
                data={"state": StreamState.IDLE.value}
            ))
    
    def push_audio(self, audio_data: bytes, sample_rate: int = 16000):
        """
        推送音频数据
        
        Args:
            audio_data: PCM 音频数据 (16-bit)
            sample_rate: 采样率
        """
        if not self._is_running:
            return
        
        chunk = AudioChunk(
            data=audio_data,
            timestamp=time.time(),
            sample_rate=sample_rate,
        )
        
        self._audio_buffer.push(chunk)
        self._chunks_received += 1
        
        # VAD 检测
        vad_result = self._vad.process_chunk(audio_data)
        
        if vad_result["is_start"]:
            self._emit(StreamEvent(
                type="vad",
                data={"event": "speech_start", "energy": vad_result["energy"]}
            ))
        
        if vad_result["is_end"]:
            self._emit(StreamEvent(
                type="vad",
                data={"event": "speech_end", "energy": vad_result["energy"]}
            ))
            # 触发识别
            self._transcribe_buffer()
    
    def _transcribe_buffer(self):
        """识别缓冲区中的音频"""
        if not self._asr_callback:
            return
        
        audio_data = self._audio_buffer.get_all()
        if len(audio_data) < 1000:  # 太短的数据不处理
            return
        
        self._state = StreamState.PROCESSING
        self._emit(StreamEvent(
            type="state",
            data={"state": StreamState.PROCESSING.value}
        ))
        
        try:
            segment = self._asr_callback(audio_data)
            self._segments_transcribed += 1
            
            self._emit(StreamEvent(
                type="transcript",
                data={
                    "text": segment.text,
                    "is_final": segment.is_final,
                    "confidence": segment.confidence,
                    "language": segment.language,
                }
            ))
            
            # 清空已识别的缓冲
            if segment.is_final:
                self._audio_buffer.clear()
        except Exception as e:
            self._emit(StreamEvent(
                type="error",
                data={"error": str(e)}
            ))
        finally:
            self._state = StreamState.CONNECTED
    
    async def speak(self, text: str):
        """播放语音"""
        if not self._tts_callback:
            return
        
        self._state = StreamState.SPEAKING
        self._emit(StreamEvent(
            type="state",
            data={"state": StreamState.SPEAKING.value}
        ))
        
        try:
            async for audio_chunk in self._tts_callback(text):
                self._emit(StreamEvent(
                    type="audio",
                    data={"audio": base64.b64encode(audio_chunk).decode()}
                ))
        except Exception as e:
            self._emit(StreamEvent(
                type="error",
                data={"error": str(e)}
            ))
        finally:
            self._state = StreamState.CONNECTED
    
    def interrupt(self):
        """打断当前播放"""
        self._state = StreamState.CONNECTED
        self._emit(StreamEvent(
            type="interrupt",
            data={}
        ))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        uptime = time.time() - self._start_time if self._start_time else 0
        return {
            "state": self._state.value,
            "uptime_seconds": uptime,
            "chunks_received": self._chunks_received,
            "segments_transcribed": self._segments_transcribed,
            "buffer_duration": self._audio_buffer.duration,
        }


class WebSocketVoiceHandler:
    """
    WebSocket 语音处理器
    处理 WebSocket 连接的语音流
    """
    
    def __init__(self, stream: RealtimeVoiceStream):
        self._stream = stream
        self._connections: Set[Any] = set()
        self._lock = threading.Lock()
        
        # 注册事件监听
        stream.add_listener(self._on_stream_event)
    
    async def handle_connection(self, websocket, path: str = "/ws/voice"):
        """处理 WebSocket 连接"""
        with self._lock:
            self._connections.add(websocket)
        
        try:
            self._stream.start()
            
            async for message in websocket:
                if isinstance(message, bytes):
                    # 二进制音频数据
                    self._stream.push_audio(message)
                elif isinstance(message, str):
                    # JSON 控制消息
                    try:
                        data = json.loads(message)
                        await self._handle_control(websocket, data)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"[WebSocket] Error: {e}")
        finally:
            with self._lock:
                self._connections.discard(websocket)
            if not self._connections:
                self._stream.stop()
    
    async def _handle_control(self, websocket, data: Dict[str, Any]):
        """处理控制消息"""
        action = data.get("action")
        
        if action == "start":
            self._stream.start()
        elif action == "stop":
            self._stream.stop()
        elif action == "interrupt":
            self._stream.interrupt()
        elif action == "speak":
            text = data.get("text", "")
            await self._stream.speak(text)
        elif action == "config":
            # 更新配置
            pass
    
    def _on_stream_event(self, event: StreamEvent):
        """处理流事件，广播给所有连接"""
        message = json.dumps({
            "type": event.type,
            "data": event.data,
            "timestamp": event.timestamp,
        })
        
        # 广播给所有连接
        with self._lock:
            connections = list(self._connections)
        
        for ws in connections:
            try:
                asyncio.create_task(ws.send(message))
            except Exception:
                pass
    
    def broadcast(self, message: str):
        """广播消息"""
        with self._lock:
            connections = list(self._connections)
        
        for ws in connections:
            try:
                asyncio.create_task(ws.send(message))
            except Exception:
                pass


# 全局实例
_voice_stream: Optional[RealtimeVoiceStream] = None
_stream_lock = threading.Lock()


def get_voice_stream(
    asr_callback: Optional[Callable] = None,
    tts_callback: Optional[Callable] = None,
) -> RealtimeVoiceStream:
    """获取全局语音流实例"""
    global _voice_stream
    if _voice_stream is None:
        with _stream_lock:
            if _voice_stream is None:
                _voice_stream = RealtimeVoiceStream(asr_callback, tts_callback)
    return _voice_stream
