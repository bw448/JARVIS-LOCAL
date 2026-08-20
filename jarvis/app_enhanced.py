"""
增强版应用模块 - v0.8.0
集成Memory、Skills、Web Search、Computer Use和性能监控
参考 Aivy OS 架构设计
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.parse import unquote, urlparse

from . import __version__
from .brain import BrainError, OpenAICompatibleBrain, normalize_messages
from .config import ConfigError, Settings, SettingsStore, default_data_dir
from .computer_use import ComputerUseService, ComputerUseError
from .secrets import SecretStore, SecretStoreError
from .speech import AudioResult, SpeechError, SpeechService
from .speech_optimizer import get_tts_cache, get_metrics
from .speech_patch import patch_speech_service
from .app_integration import get_context_builder


STATIC_DIR = Path(__file__).with_name("static")
APP_NAME = "JARVIS LOCAL"
APP_VERSION = __version__

VOICE_EMOTION_LABELS = {
    "happy": "愉快",
    "sad": "低落或难过",
    "angry": "生气或烦躁",
    "neutral": "平静",
    "fearful": "紧张或害怕",
    "disgusted": "反感",
    "surprised": "惊讶",
}


def voice_context_from_payload(payload: Mapping[str, Any]) -> str:
    raw = payload.get("voice_context")
    if not isinstance(raw, Mapping):
        return ""
    emotion = str(raw.get("emotion", "")).strip().lower()
    label = VOICE_EMOTION_LABELS.get(emotion)
    if not label or emotion == "neutral":
        return ""
    return (
        f"本轮由本地语音模型检测到用户声音可能显得{label}。"
        "这只是可能出错的弱提示：结合用户实际文字自然回应，不要直接宣称已经识破其情绪。"
    )


class EnhancedJarvisApplication:
    """
    增强版贾维斯应用 - v0.8.0
    集成 Memory、Skills、Web Search、Computer Use
    参考 Aivy OS 架构设计
    """

    def __init__(
        self,
        settings_store: SettingsStore | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.settings_store = settings_store or SettingsStore()
        self.secret_store = secret_store or SecretStore()
        self.speech = SpeechService()
        self.brain = OpenAICompatibleBrain()
        self.computer = ComputerUseService()

        # 应用语音缓存补丁
        self.speech = patch_speech_service(self.speech)

        # 初始化增强功能
        self._context_builder = get_context_builder()

        self._lock = threading.RLock()
        self._settings = self.settings_store.load()
        self._prewarm_lock = threading.Lock()
        self._prewarm_generation = 0
        self._prewarm_state: Dict[str, Any] = {
            "status": "idle",
            "components": {},
        }

    @property
    def settings(self) -> Settings:
        with self._lock:
            return self._settings

    @property
    def memory(self):
        """Access memory store."""
        return self._context_builder.memory

    @property
    def skills(self):
        """Access skill manager."""
        return self._context_builder.skills

    @property
    def search(self):
        """Access search service."""
        return self._context_builder.search

    def _runtime_snapshot(self) -> Dict[str, Any]:
        with self._prewarm_lock:
            return {
                "status": self._prewarm_state["status"],
                "components": dict(self._prewarm_state["components"]),
            }

    def _capabilities(self, settings: Settings) -> Dict[str, Any]:
        capabilities = self.speech.capabilities(settings)
        runtime = self._runtime_snapshot()
        components = runtime["components"]
        if (
            settings.stt.provider == "sensevoice"
            and runtime["status"] == "degraded"
            and components.get("stt") != "ready"
        ):
            capabilities["stt"]["ready"] = False
            capabilities["stt"]["reason"] = "worker_unreachable"
        if (
            settings.tts.provider == "external"
            and runtime["status"] == "degraded"
            and components.get("tts") != "ready"
        ):
            capabilities["tts"]["ready"] = False
            capabilities["tts"]["reason"] = "worker_unreachable"
        return capabilities

    def _build_enhanced_system_prompt(self, settings: Settings) -> str:
        """Build enhanced system prompt with memory and skills context."""
        return self._context_builder.build_system_context(settings)

    def complete(
        self,
        messages: list,
        api_key: str = "",
        voice_context: str = "",
        use_tools: bool = True,
    ) -> str:
        """Complete a conversation with enhanced context."""
        settings = self.settings

        # Process user message through context builder
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict) and last_msg.get("role") == "user":
                self._context_builder.process_user_message(last_msg.get("content", ""))

        # Build enhanced system prompt
        enhanced_prompt = self._build_enhanced_system_prompt(settings)

        # Get tool definitions if enabled
        tools = self._context_builder.get_tool_definitions() if use_tools else None

        # Use brain with enhanced context
        from .brain import ChatMessage
        chat_messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]

        # Override system prompt
        original_system_prompt = settings.system_prompt
        settings._system_prompt_override = enhanced_prompt

        try:
            result = self.brain.complete(
                settings,
                chat_messages,
                api_key=api_key,
                voice_context=voice_context,
            )
        finally:
            settings._system_prompt_override = None

        # Store assistant response in memory
        self._context_builder.process_user_message(result, role="assistant")

        return result

    def stream(
        self,
        messages: list,
        api_key: str = "",
        voice_context: str = "",
        use_tools: bool = True,
    ) -> Iterator[str]:
        """Stream a conversation with enhanced context."""
        settings = self.settings

        # Process user message through context builder
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict) and last_msg.get("role") == "user":
                self._context_builder.process_user_message(last_msg.get("content", ""))

        # Build enhanced system prompt
        enhanced_prompt = self._build_enhanced_system_prompt(settings)

        # Get tool definitions if enabled
        tools = self._context_builder.get_tool_definitions() if use_tools else None

        # Use brain with enhanced context
        from .brain import ChatMessage
        chat_messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]

        # Override system prompt
        original_system_prompt = settings.system_prompt
        settings._system_prompt_override = enhanced_prompt

        try:
            full_response = []
            for event in self.brain.stream_events(
                settings,
                chat_messages,
                api_key=api_key,
                voice_context=voice_context,
                tools=tools,
            ):
                if isinstance(event, dict):
                    if event.get("type") == "text":
                        full_response.append(event.get("text", ""))
                        yield event
                    elif event.get("type") == "tool_call":
                        # Handle tool calls
                        tool_name = event.get("name", "")
                        tool_args = event.get("arguments", {})
                        tool_result = self._context_builder.execute_tool(tool_name, tool_args)
                        yield {"type": "tool_result", "tool_name": tool_name, "result": tool_result}
                    else:
                        yield event
                else:
                    yield event
        finally:
            settings._system_prompt_override = None

        # Store assistant response in memory
        if full_response:
            self._context_builder.process_user_message("".join(full_response), role="assistant")

    def search_web(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Perform a web search."""
        try:
            response = self.search.search(query, max_results=max_results)
            return response.to_dict()
        except Exception as e:
            return {"error": str(e)}

    def remember(self, content: str, category: str = "fact", importance: float = 0.6) -> str:
        """Store something in long-term memory."""
        return self.memory.remember(content, category=category, importance=importance)

    def recall(self, query: str, limit: int = 5) -> list:
        """Search long-term memory."""
        results = self.memory.recall(query, limit=limit)
        return [{"content": r.content, "category": r.category, "importance": r.importance} for r in results]

    def get_stats(self) -> Dict[str, Any]:
        """Get application statistics."""
        stats = self._context_builder.get_stats()
        stats["version"] = APP_VERSION
        stats["speech_metrics"] = get_metrics().get_stats() if hasattr(get_metrics(), 'get_stats') else {}
        return stats


def create_enhanced_server(
    host: str = "127.0.0.1",
    port: int = 0,
    settings_store: SettingsStore | None = None,
    secret_store: SecretStore | None = None,
) -> tuple[ThreadingHTTPServer, type[BaseHTTPRequestHandler]]:
    """Create enhanced HTTP server."""
    app = EnhancedJarvisApplication(
        settings_store=settings_store,
        secret_store=secret_store,
    )

    class EnhancedHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path

            if path == "/" or path == "/index.html":
                self._serve_file(STATIC_DIR / "index.html", "text/html")
            elif path == "/api/stats":
                self._json_response(app.get_stats())
            elif path == "/api/memory/stats":
                self._json_response(app.memory.get_memory_stats())
            elif path == "/api/skills":
                self._json_response(app.skills.list_skills())
            elif path.startswith("/static/"):
                file_path = STATIC_DIR / path[8:]
                if file_path.exists():
                    content_type, _ = mimetypes.guess_type(str(file_path))
                    self._serve_file(file_path, content_type or "application/octet-stream")
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_response({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return

            path = urlparse(self.path).path

            if path == "/api/chat":
                self._handle_chat(data)
            elif path == "/api/search":
                self._handle_search(data)
            elif path == "/api/memory/remember":
                self._handle_remember(data)
            elif path == "/api/memory/recall":
                self._handle_recall(data)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def _serve_file(self, file_path: Path, content_type: str):
            if not file_path.exists():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)

        def _json_response(self, data: Any, status: HTTPStatus = HTTPStatus.OK):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        def _handle_chat(self, data: Dict[str, Any]):
            messages = data.get("messages", [])
            api_key = data.get("api_key", "")
            voice_context = voice_context_from_payload(data)

            if data.get("stream"):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                for event in app.stream(messages, api_key=api_key, voice_context=voice_context):
                    line = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
            else:
                result = app.complete(messages, api_key=api_key, voice_context=voice_context)
                self._json_response({"content": result})

        def _handle_search(self, data: Dict[str, Any]):
            query = data.get("query", "")
            max_results = data.get("max_results", 5)
            result = app.search_web(query, max_results=max_results)
            self._json_response(result)

        def _handle_remember(self, data: Dict[str, Any]):
            content = data.get("content", "")
            category = data.get("category", "fact")
            importance = data.get("importance", 0.6)
            entry_id = app.remember(content, category=category, importance=importance)
            self._json_response({"id": entry_id, "status": "stored"})

        def _handle_recall(self, data: Dict[str, Any]):
            query = data.get("query", "")
            limit = data.get("limit", 5)
            results = app.recall(query, limit=limit)
            self._json_response({"results": results})

        def log_message(self, format, *args):
            pass  # Suppress request logs

    server = ThreadingHTTPServer((host, port), EnhancedHandler)
    return server, EnhancedHandler


def run_enhanced_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    settings_store: SettingsStore | None = None,
    secret_store: SecretStore | None = None,
):
    """Run the enhanced server."""
    server, _ = create_enhanced_server(
        host=host,
        port=port,
        settings_store=settings_store,
        secret_store=secret_store,
    )
    print(f"[JARVIS] Enhanced server running on http://{host}:{port}")
    server.serve_forever()
