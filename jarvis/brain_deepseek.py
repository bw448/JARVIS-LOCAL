"""
DeepSeek Harness Brain Adapter for JARVIS.

Integrates DeepSeek Harness Python SDK as an alternative brain provider,
enabling JARVIS to leverage DeepSeek Harness's plugin-based agent architecture.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

from .brain import BrainError, ChatMessage, normalize_messages
from .config import Settings

logger = logging.getLogger(__name__)

# Try to import DeepSeek Harness SDK
DSH_AVAILABLE = False
DeepSeekHarness = None
DeepSeekHarnessConfig = None

try:
    from deepseek_harness import (
        DeepSeekHarness as _DeepSeekHarness,
        DeepSeekHarnessConfig as _DeepSeekHarnessConfig,
        RunResult,
        Session,
    )
    DeepSeekHarness = _DeepSeekHarness
    DeepSeekHarnessConfig = _DeepSeekHarnessConfig
    DSH_AVAILABLE = True
except ImportError:
    logger.info("DeepSeek Harness SDK not installed. Using OpenAI-compatible brain only.")


@dataclass
class DSHBrainConfig:
    """Configuration for DeepSeek Harness brain."""
    
    enabled: bool = True
    model: str = "deepseek-chat"
    provider: str = "deepseek-official"
    max_tokens: Optional[int] = None
    runtime_bin: Optional[str] = None
    session_root: Optional[str] = None
    cordis_config: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    request_timeout: float = 180.0
    shutdown_timeout: float = 5.0
    fallback_to_openai: bool = True
    env_overrides: Dict[str, str] = field(default_factory=dict)


class DeepSeekHarnessBrain:
    """Brain implementation using DeepSeek Harness Python SDK."""
    
    def __init__(self, config: Optional[DSHBrainConfig] = None):
        self.config = config or DSHBrainConfig()
        self._harness: Optional[Any] = None
        self._lock = threading.Lock()
        self._initialized = False
        self._startup_error: Optional[str] = None
        
        if not DSH_AVAILABLE:
            self._startup_error = "DeepSeek Harness SDK 未安装"
            logger.warning(self._startup_error)
    
    @property
    def is_available(self) -> bool:
        """Check if DSH brain is available."""
        return DSH_AVAILABLE and self._startup_error is None
    
    def _ensure_initialized(self, settings: Settings) -> None:
        """Lazy initialization of the DeepSeek Harness runtime."""
        if self._initialized and self._harness is not None:
            return
        
        if not DSH_AVAILABLE:
            raise BrainError("DeepSeek Harness SDK 未安装。请运行: pip install deepseek-harness-sdk")
            
        with self._lock:
            if self._initialized:
                return
                
            config = self._build_config(settings)
            
            try:
                self._harness = DeepSeekHarness(config)
                self._harness.start()
                self._initialized = True
                logger.info("DeepSeek Harness initialized successfully")
            except Exception as e:
                self._startup_error = str(e)
                logger.error(f"Failed to initialize DeepSeek Harness: {e}")
                raise BrainError(f"DeepSeek Harness 初始化失败: {e}")
    
    def _build_config(self, settings: Settings) -> Any:
        """Build DeepSeekHarnessConfig from JARVIS settings."""
        config = self.config
        
        api_key = config.api_key or settings.brain.api_key or ""
        base_url = config.base_url or settings.brain.base_url
        
        env = dict(config.env_overrides)
        
        return DeepSeekHarnessConfig(
            provider=config.provider,
            model=config.model or settings.brain.model,
            max_tokens=config.max_tokens,
            cwd=str(Path.cwd()),
            session_root=config.session_root,
            cordis=config.cordis_config,
            env=env,
            runtime_bin=config.runtime_bin,
            request_timeout_seconds=config.request_timeout,
            shutdown_timeout_seconds=config.shutdown_timeout,
            base_url=base_url,
            api_key=api_key,
        )
    
    def complete(
        self,
        settings: Settings,
        messages: List[ChatMessage],
        api_key: str = "",
        voice_context: str = "",
    ) -> str:
        """Complete a conversation using DeepSeek Harness."""
        if not self.config.enabled:
            raise BrainError("DeepSeek Harness 已禁用")
        
        self._ensure_initialized(settings)
        
        prompt = self._build_prompt(messages, voice_context)
        
        try:
            result = self._harness.run(
                prompt,
                session_id=f"jarvis-{id(messages)}",
            )
            
            if not result.final_response:
                raise BrainError("DeepSeek Harness 没有返回响应")
            
            return result.final_response
            
        except Exception as e:
            logger.error(f"DeepSeek Harness error: {e}")
            raise BrainError(f"DeepSeek Harness 错误: {e}")
    
    def stream(
        self,
        settings: Settings,
        messages: List[ChatMessage],
        api_key: str = "",
        voice_context: str = "",
    ) -> Iterator[str]:
        """Stream response from DeepSeek Harness."""
        response = self.complete(settings, messages, api_key, voice_context)
        yield response
    
    def _build_prompt(self, messages: List[ChatMessage], voice_context: str = "") -> str:
        """Build a prompt string from JARVIS messages."""
        parts = []
        
        for msg in messages:
            if msg.role == "user":
                parts.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                parts.append(f"Assistant: {msg.content}")
        
        if voice_context:
            parts.insert(0, f"[Voice Context: {voice_context}]")
        
        return "\n".join(parts)
    
    def close(self) -> None:
        """Clean up DeepSeek Harness resources."""
        with self._lock:
            if self._harness is not None:
                try:
                    self._harness.close()
                except Exception as e:
                    logger.warning(f"Error closing DeepSeek Harness: {e}")
                finally:
                    self._harness = None
                    self._initialized = False
    
    def __del__(self):
        self.close()


class HybridBrain:
    """Hybrid brain that switches between DeepSeek Harness and OpenAI-compatible.
    
    Priority:
    1. DeepSeek Harness (if enabled and available)
    2. OpenAI-compatible brain (fallback)
    """
    
    def __init__(
        self,
        openai_brain: Any,
        dsh_config: Optional[DSHBrainConfig] = None,
    ):
        self.openai_brain = openai_brain
        self.dsh_config = dsh_config or DSHBrainConfig()
        self._dsh_brain: Optional[DeepSeekHarnessBrain] = None
        
        if self.dsh_config.enabled:
            try:
                self._dsh_brain = DeepSeekHarnessBrain(self.dsh_config)
                if not self._dsh_brain.is_available:
                    logger.info("DSH SDK not available, will use OpenAI brain")
            except Exception as e:
                logger.warning(f"Failed to initialize DSH brain: {e}")
    
    @property
    def active_brain(self) -> str:
        """Return which brain is currently active."""
        if self._dsh_brain and self._dsh_brain.is_available and self.dsh_config.enabled:
            return "deepseek-harness"
        return "openai-compatible"
    
    def complete(
        self,
        settings: Settings,
        messages: List[ChatMessage],
        api_key: str = "",
        voice_context: str = "",
    ) -> str:
        """Complete using the best available brain."""
        # Try DeepSeek Harness first if enabled and available
        if (self._dsh_brain and 
            self._dsh_brain.is_available and 
            self.dsh_config.enabled):
            try:
                return self._dsh_brain.complete(settings, messages, api_key, voice_context)
            except Exception as e:
                if self.dsh_config.fallback_to_openai:
                    logger.warning(f"DSH brain failed, falling back to OpenAI: {e}")
                else:
                    raise
        
        # Fall back to OpenAI-compatible brain
        return self.openai_brain.complete(settings, messages, api_key, voice_context)
    
    def stream(
        self,
        settings: Settings,
        messages: List[ChatMessage],
        api_key: str = "",
        voice_context: str = "",
    ) -> Iterator[str]:
        """Stream using the best available brain."""
        if (self._dsh_brain and 
            self._dsh_brain.is_available and 
            self.dsh_config.enabled):
            try:
                yield from self._dsh_brain.stream(settings, messages, api_key, voice_context)
                return
            except Exception as e:
                if self.dsh_config.fallback_to_openai:
                    logger.warning(f"DSH brain stream failed, falling back to OpenAI: {e}")
                else:
                    raise
        
        yield from self.openai_brain.stream(settings, messages, api_key, voice_context)
    
    def close(self) -> None:
        """Clean up resources."""
        if self._dsh_brain:
            self._dsh_brain.close()
