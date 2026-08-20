"""
本地 LLM 集成优化 - v1.1.0
支持 llama.cpp、Ollama、vLLM 等本地模型
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterator
from urllib import error, request


class LLMProvider(Enum):
    """LLM 提供商"""
    LLAMACPP = "llamacpp"
    OLLAMA = "ollama"
    VLLM = "vllm"
    OPENAI_COMPATIBLE = "openai_compatible"


@dataclass(slots=True)
class LLMConfig:
    """LLM 配置"""
    provider: LLMProvider = LLMProvider.OPENAI_COMPATIBLE
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "local-model"
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 120
    context_length: int = 4096
    
    # llama.cpp 特定配置
    llamacpp_path: str = ""
    llamacpp_model_path: str = ""
    llamacpp_gpu_layers: int = 0
    llamacpp_threads: int = 4
    
    # Ollama 特定配置
    ollama_model: str = "llama2"


@dataclass(slots=True)
class LLMStatus:
    """LLM 状态"""
    provider: str
    model: str
    is_running: bool
    pid: Optional[int] = None
    port: Optional[int] = None
    uptime: float = 0.0
    requests_served: int = 0
    memory_usage_mb: float = 0.0


class LlamaCppManager:
    """
    llama.cpp 管理器
    管理 llama-server 进程
    """
    
    def __init__(self, config: LLMConfig):
        self._config = config
        self._process: Optional[subprocess.Popen] = None
        self._is_running = False
        self._start_time = 0.0
        self._lock = threading.Lock()
    
    @property
    def is_running(self) -> bool:
        return self._is_running and self._process is not None and self._process.poll() is None
    
    def start(self, model_path: str = "", port: int = 8080) -> bool:
        """启动 llama-server"""
        with self._lock:
            if self.is_running:
                return True
            
            model = model_path or self._config.llamacpp_model_path
            if not model:
                print("[LlamaCpp] No model path specified")
                return False
            
            llamacpp = self._config.llamacpp_path or "llama-server"
            
            cmd = [
                llamacpp,
                "--model", model,
                "--port", str(port),
                "--ctx-size", str(self._config.context_length),
                "--threads", str(self._config.llamacpp_threads),
            ]
            
            if self._config.llamacpp_gpu_layers > 0:
                cmd.extend(["--n-gpu-layers", str(self._config.llamacpp_gpu_layers)])
            
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                
                # 等待启动
                time.sleep(2)
                
                if self._process.poll() is None:
                    self._is_running = True
                    self._start_time = time.time()
                    print(f"[LlamaCpp] Started on port {port}, PID: {self._process.pid}")
                    return True
                else:
                    stdout = self._process.stdout.read().decode() if self._process.stdout else ""
                    stderr = self._process.stderr.read().decode() if self._process.stderr else ""
                    print(f"[LlamaCpp] Failed to start: {stderr[:200]}")
                    return False
            except FileNotFoundError:
                print(f"[LlamaCpp] Executable not found: {llamacpp}")
                return False
            except Exception as e:
                print(f"[LlamaCpp] Start failed: {e}")
                return False
    
    def stop(self):
        """停止 llama-server"""
        with self._lock:
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None
                self._is_running = False
                print("[LlamaCpp] Stopped")
    
    def get_status(self) -> LLMStatus:
        """获取状态"""
        return LLMStatus(
            provider="llamacpp",
            model=self._config.llamacpp_model_path,
            is_running=self.is_running,
            pid=self._process.pid if self._process else None,
            uptime=time.time() - self._start_time if self._start_time else 0,
        )


class OllamaManager:
    """
    Ollama 管理器
    管理 Ollama 模型
    """
    
    def __init__(self, config: LLMConfig):
        self._config = config
        self._base_url = "http://localhost:11434"
    
    def is_running(self) -> bool:
        """检查 Ollama 是否运行"""
        try:
            req = request.Request(f"{self._base_url}/api/tags", method="GET")
            with request.urlopen(req, timeout=5):
                return True
        except:
            return False
    
    def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        try:
            req = request.Request(f"{self._base_url}/api/tags", method="GET")
            with request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("models", [])
        except:
            return []
    
    def pull_model(self, model: str) -> bool:
        """拉取模型"""
        try:
            payload = {"name": model}
            req = request.Request(
                f"{self._base_url}/api/pull",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with request.urlopen(req, timeout=300) as resp:
                # 流式响应
                for line in resp:
                    data = json.loads(line.decode("utf-8"))
                    if data.get("status"):
                        print(f"[Ollama] {data['status']}")
                
                return True
        except Exception as e:
            print(f"[Ollama] Pull failed: {e}")
            return False
    
    def get_status(self) -> LLMStatus:
        """获取状态"""
        running = self.is_running()
        models = self.list_models() if running else []
        
        return LLMStatus(
            provider="ollama",
            model=self._config.ollama_model,
            is_running=running,
            requests_served=len(models),
        )


class LocalLLMService:
    """
    本地 LLM 服务
    统一接口访问不同的本地模型
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self._config = config or LLMConfig()
        self._llamacpp = LlamaCppManager(self._config)
        self._ollama = OllamaManager(self._config)
        self._lock = threading.RLock()
    
    @property
    def config(self) -> LLMConfig:
        return self._config
    
    def start(self) -> bool:
        """启动本地 LLM"""
        provider = self._config.provider
        
        if provider == LLMProvider.LLAMACPP:
            return self._llamacpp.start()
        elif provider == LLMProvider.OLLAMA:
            return self._ollama.is_running()
        else:
            # 检查 OpenAI 兼容接口
            return self._check_api()
    
    def stop(self):
        """停止本地 LLM"""
        if self._config.provider == LLMProvider.LLAMACPP:
            self._llamacpp.stop()
    
    def _check_api(self) -> bool:
        """检查 API 是否可用"""
        try:
            req = request.Request(
                f"{self._config.base_url}/models",
                headers={"Authorization": f"Bearer {self._config.api_key}"} if self._config.api_key else {},
                method="GET"
            )
            with request.urlopen(req, timeout=5):
                return True
        except:
            return False
    
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Any:
        """
        完成对话
        
        Args:
            messages: 消息列表
            temperature: 温度
            max_tokens: 最大 token 数
            stream: 是否流式
            
        Returns:
            响应内容
        """
        url = f"{self._config.base_url}/chat/completions"
        
        payload = {
            "model": self._config.model,
            "messages": messages,
            "temperature": temperature or self._config.temperature,
            "max_tokens": max_tokens or self._config.max_tokens,
            "stream": stream,
        }
        
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        if stream:
            return self._stream_request(req)
        else:
            return self._sync_request(req)
    
    def _sync_request(self, req: request.Request) -> Dict[str, Any]:
        """同步请求"""
        try:
            with request.urlopen(req, timeout=self._config.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}") from e
    
    def _stream_request(self, req: request.Request) -> Iterator[Dict[str, Any]]:
        """流式请求"""
        try:
            with request.urlopen(req, timeout=self._config.timeout) as resp:
                for line in resp:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            raise RuntimeError(f"LLM stream failed: {e}") from e
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        if self._config.provider == LLMProvider.LLAMACPP:
            status = self._llamacpp.get_status()
        elif self._config.provider == LLMProvider.OLLAMA:
            status = self._ollama.get_status()
        else:
            status = LLMStatus(
                provider=self._config.provider if isinstance(self._config.provider, str) else self._config.provider.value,
                model=self._config.model,
                is_running=self._check_api(),
            )
        
        return {
            "provider": status.provider,
            "model": status.model,
            "is_running": status.is_running,
            "pid": status.pid,
            "uptime": status.uptime,
        }
    
    def list_ollama_models(self) -> List[Dict[str, Any]]:
        """列出 Ollama 模型"""
        return self._ollama.list_models()
    
    def pull_ollama_model(self, model: str) -> bool:
        """拉取 Ollama 模型"""
        return self._ollama.pull_model(model)


# 全局实例
_llm_service: Optional[LocalLLMService] = None
_llm_lock = threading.Lock()


def get_llm_service(config: Optional[LLMConfig] = None) -> LocalLLMService:
    """获取全局 LLM 服务"""
    global _llm_service
    if _llm_service is None:
        with _llm_lock:
            if _llm_service is None:
                _llm_service = LocalLLMService(config)
    return _llm_service


# 工具定义
LLM_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "llm_status",
            "description": "获取本地 LLM 状态",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "llm_list_models",
            "description": "列出可用的本地模型",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]
