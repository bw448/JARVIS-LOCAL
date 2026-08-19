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
from .config import ConfigError, Settings, SettingsStore
from .computer import ComputerToolError, ComputerToolService
from .secrets import SecretStore, SecretStoreError
from .speech import AudioResult, SpeechError, SpeechService


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


class JarvisApplication:
    def __init__(
        self,
        settings_store: SettingsStore | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.settings_store = settings_store or SettingsStore()
        self.secret_store = secret_store or SecretStore()
        self.speech = SpeechService()
        self.brain = OpenAICompatibleBrain()
        self.computer = ComputerToolService()
        self._lock = threading.RLock()
        self._settings = self.settings_store.load()
        self._prewarm_lock = threading.Lock()
        self._prewarm_generation = 0
        self._prewarm_state: dict[str, Any] = {
            "status": "idle",
            "components": {},
        }

    @property
    def settings(self) -> Settings:
        with self._lock:
            return self._settings

    def _runtime_snapshot(self) -> dict[str, Any]:
        with self._prewarm_lock:
            return {
                "status": self._prewarm_state["status"],
                "components": dict(self._prewarm_state["components"]),
            }

    def _capabilities(self, settings: Settings) -> dict[str, Any]:
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

    def public_state(self) -> dict[str, Any]:
        settings = self.settings
        prewarm_state = self._runtime_snapshot()
        return {
            "app": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "display_name": settings.identity.assistant_name,
                "edition": "local-first",
            },
            "settings": settings.to_dict(),
            "secrets": {"brain_api_key_saved": self.secret_store.has_brain_api_key()},
            "capabilities": self._capabilities(settings),
            "runtime": {"prewarm": prewarm_state},
            "computer_control": {
                "available": self.computer.available,
                "enabled": settings.interaction.computer_control_enabled,
                "confirmation_required_for_changes": True,
            },
        }

    def start_prewarm(self) -> bool:
        settings = self.settings
        if not settings.interaction.prewarm_models:
            with self._prewarm_lock:
                self._prewarm_generation += 1
                self._prewarm_state = {"status": "disabled", "components": {}}
            return False
        with self._prewarm_lock:
            self._prewarm_generation += 1
            generation = self._prewarm_generation
            self._prewarm_state = {"status": "loading", "components": {}}

        def worker() -> None:
            try:
                components = self.speech.prewarm(settings)
            except Exception as exc:
                components = {"runtime": f"{type(exc).__name__}: {exc}"}
            with self._prewarm_lock:
                if generation != self._prewarm_generation:
                    return
                failures = [value for value in components.values() if value != "ready"]
                self._prewarm_state = {
                    "status": "degraded" if failures else "ready",
                    "components": components,
                }

        threading.Thread(target=worker, name="jarvis-model-prewarm", daemon=True).start()
        return True

    def voice_state(self) -> dict[str, Any]:
        settings = self.settings
        settings_raw = settings.to_dict()
        return {
            "capabilities": self._capabilities(settings),
            "settings": {
                "tts": settings_raw["tts"],
                "stt": settings_raw["stt"],
            },
            "runtime": {"prewarm": self._runtime_snapshot()},
        }

    def voice_test(self, payload: Any = None) -> tuple[str, AudioResult | None]:
        settings = self.settings
        if payload is not None:
            if not isinstance(payload, Mapping):
                raise ConfigError("试听设置格式无效")
            settings_raw = payload.get("settings", payload)
            if not isinstance(settings_raw, Mapping):
                raise ConfigError("试听设置格式无效")
            settings = Settings.from_mapping(settings_raw)
        if settings.tts.provider != "system" and settings.tts.browser_fallback:
            settings = Settings.from_mapping(settings.to_dict())
            settings.tts.browser_fallback = False
        text = (
            f"{settings.identity.owner_name}，你好呀，我是"
            f"{settings.identity.assistant_name}。很高兴为你服务，今天也请多多关照。"
        )
        return text, self.speech.synthesize(settings, text)

    def update_settings(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ConfigError("设置数据格式无效")
        settings_raw = payload.get("settings", payload)
        if not isinstance(settings_raw, Mapping):
            raise ConfigError("设置数据格式无效")
        updated = Settings.from_mapping(settings_raw)

        api_key_action = payload.get("api_key_action", "keep")
        if api_key_action not in {"keep", "set", "clear"}:
            raise ConfigError("密钥操作无效")
        if api_key_action == "set":
            api_key = str(payload.get("api_key", "")).strip()
            if not api_key:
                raise ConfigError("要保存的 API 密钥不能为空")
            self.secret_store.set_brain_api_key(api_key)
        elif api_key_action == "clear":
            self.secret_store.set_brain_api_key("")

        previous = self.settings
        self.settings_store.save(updated)
        with self._lock:
            self._settings = updated
        if previous.tts != updated.tts:
            self.speech.clear_tts_cache()
        if previous.tts != updated.tts or previous.stt != updated.stt:
            self.start_prewarm()
        return self.public_state()

    def chat(self, payload: Any) -> str:
        if not isinstance(payload, Mapping):
            raise BrainError("请求格式无效")
        messages = normalize_messages(payload.get("messages"))
        settings = self.settings
        return self.brain.complete(
            settings,
            messages,
            api_key=self.secret_store.get_brain_api_key(),
            voice_context=voice_context_from_payload(payload),
        )

    def chat_stream(self, payload: Any) -> Iterator[dict[str, Any]]:
        if not isinstance(payload, Mapping):
            raise BrainError("请求格式无效")
        messages = normalize_messages(payload.get("messages"))
        settings = self.settings
        api_key = self.secret_store.get_brain_api_key()
        voice_context = voice_context_from_payload(payload)
        started = time.perf_counter()
        first_token_ms: int | None = None
        answer_parts: list[str] = []
        streamed = False
        tool_count = 0

        try:
            tooling_enabled = (
                settings.interaction.computer_control_enabled and self.computer.available
            )
            if tooling_enabled:
                events = self.brain.stream_events(
                    settings,
                    messages,
                    api_key=api_key,
                    voice_context=voice_context,
                    tools=self.computer.schemas(),
                )
            else:
                events = (
                    {"type": "text", "text": delta}
                    for delta in self.brain.stream(
                        settings,
                        messages,
                        api_key=api_key,
                        voice_context=voice_context,
                    )
                )

            for event in events:
                if first_token_ms is None:
                    first_token_ms = round((time.perf_counter() - started) * 1000)
                streamed = True
                if event["type"] == "text":
                    delta = str(event.get("text", ""))
                    answer_parts.append(delta)
                    yield {"type": "delta", "text": delta}
                    continue
                if event["type"] != "tool_call":
                    continue
                tool_count += 1
                if tool_count > 1:
                    raise BrainError("一次对话只允许提出一个电脑操作")
                action = self.computer.propose(
                    str(event.get("name", "")), event.get("arguments")
                )
                if action["kind"] == "result":
                    message = str(action["message"])
                    answer_parts.append(message)
                    yield {"type": "tool_result", "message": message}
                else:
                    preview = str(action["preview"])
                    answer_parts.append(f"准备执行：{preview}。")
                    yield {"type": "tool_proposal", "proposal": action}
        except BrainError:
            if streamed:
                raise
            # Older OpenAI-compatible servers may reject stream=true. Keep the
            # legacy completion path as an automatic compatibility fallback.
            answer = self.brain.complete(
                settings,
                messages,
                api_key=api_key,
                voice_context=voice_context,
            )
            first_token_ms = round((time.perf_counter() - started) * 1000)
            answer_parts.append(answer)
            yield {"type": "delta", "text": answer}

        answer = "".join(answer_parts).strip()
        if not answer:
            raise BrainError("模型没有返回文字内容")
        yield {
            "type": "done",
            "answer": answer,
            "metrics": {
                "first_token_ms": first_token_ms,
                "total_ms": round((time.perf_counter() - started) * 1000),
                "streamed": streamed,
            },
        }

    def resolve_tool(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ComputerToolError("操作确认格式无效")
        if not self.settings.interaction.computer_control_enabled:
            raise ComputerToolError("电脑控制已经关闭")
        return self.computer.resolve(
            str(payload.get("proposal_id", "")),
            payload.get("approved") is True,
        )


class JarvisHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler: type[BaseHTTPRequestHandler],
        application: JarvisApplication,
    ) -> None:
        self.application = application
        super().__init__(server_address, request_handler)


class JarvisRequestHandler(BaseHTTPRequestHandler):
    server_version = "JarvisLocal/0.7"
    MAX_JSON_BYTES = 1024 * 1024

    @property
    def application(self) -> JarvisApplication:
        server = self.server
        assert isinstance(server, JarvisHTTPServer)
        return server.application

    def log_message(self, format_string: str, *args: Any) -> None:
        # Keep console logs metadata-only. Message and audio bodies are never logged.
        print(f"[JARVIS] {self.address_string()} {format_string % args}")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._trusted_host():
            self._json_error(HTTPStatus.MISDIRECTED_REQUEST, "无效的访问主机")
            return
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json({"ok": True, "version": APP_VERSION})
        elif path in {"/api/bootstrap", "/api/settings"}:
            self._send_json(self.application.public_state())
        elif path == "/api/voice/status":
            self._send_json(self.application.voice_state())
        elif path == "/":
            self._send_file(STATIC_DIR / "index.html")
        elif path == "/floating":
            self._send_file(STATIC_DIR / "floating.html")
        elif path.startswith("/static/"):
            relative = unquote(path.removeprefix("/static/"))
            candidate = (STATIC_DIR / relative).resolve()
            try:
                candidate.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self._json_error(HTTPStatus.NOT_FOUND, "文件不存在")
                return
            self._send_file(candidate)
        else:
            self._json_error(HTTPStatus.NOT_FOUND, "页面不存在")

    def do_POST(self) -> None:  # noqa: N802
        if not self._trusted_host() or not self._trusted_origin():
            self._json_error(HTTPStatus.FORBIDDEN, "请求来源无效")
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/settings":
                state = self.application.update_settings(self._read_json())
                self._send_json(state)
            elif path == "/api/chat":
                answer = self.application.chat(self._read_json())
                self._send_json({"answer": answer})
            elif path == "/api/chat/stream":
                self._send_ndjson(self.application.chat_stream(self._read_json()))
            elif path == "/api/tools/resolve":
                self._send_json(self.application.resolve_tool(self._read_json()))
            elif path == "/api/tts":
                payload = self._read_json()
                if not isinstance(payload, Mapping):
                    raise SpeechError("请求格式无效")
                started = time.perf_counter()
                result = self.application.speech.synthesize(
                    self.application.settings, str(payload.get("text", ""))
                )
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                if result is None:
                    self._send_json(
                        {
                            "mode": "browser",
                            "text": str(payload.get("text", "")),
                            "metrics": {"synthesis_ms": elapsed_ms},
                        }
                    )
                else:
                    self._send_audio(result, synthesis_ms=elapsed_ms)
            elif path == "/api/voice/test":
                text, result = self.application.voice_test(self._read_optional_json())
                if result is None:
                    self._send_json({"mode": "browser", "text": text})
                else:
                    self._send_audio(result)
            elif path == "/api/stt":
                body = self._read_body(self.application.speech.MAX_AUDIO_BYTES)
                started = time.perf_counter()
                transcript = self.application.speech.transcribe_detailed(
                    self.application.settings,
                    body,
                    self.headers.get("Content-Type", "application/octet-stream"),
                )
                self._send_json(
                    {
                        "text": transcript.text,
                        "language": transcript.language,
                        "emotion": transcript.emotion,
                        "metrics": {
                            "transcription_ms": round(
                                (time.perf_counter() - started) * 1000
                            )
                        },
                    }
                )
            else:
                self._json_error(HTTPStatus.NOT_FOUND, "接口不存在")
        except (
            ConfigError,
            BrainError,
            SpeechError,
            SecretStoreError,
            ComputerToolError,
        ) as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        except json.JSONDecodeError:
            self._json_error(HTTPStatus.BAD_REQUEST, "JSON 格式无效")
        except ValueError as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            # Return a stable error without exposing local paths or secret values.
            print(f"[JARVIS] internal error: {type(exc).__name__}: {exc}")
            self._json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "内部服务错误")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _trusted_host(self) -> bool:
        parsed = urlparse("//" + self.headers.get("Host", ""))
        return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}

    def _trusted_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        server = self.server
        assert isinstance(server, JarvisHTTPServer)
        expected_port = int(server.server_address[1])
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            and parsed.port == expected_port
        )

    def _read_body(self, maximum: int) -> bytes:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("缺少 Content-Length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Content-Length 无效") from exc
        if length < 0 or length > maximum:
            raise ValueError("请求内容过大")
        return self.rfile.read(length)

    def _read_json(self) -> Any:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type != "application/json":
            raise ValueError("接口只接受 application/json")
        body = self._read_body(self.MAX_JSON_BYTES)
        return json.loads(body.decode("utf-8"))

    def _read_optional_json(self) -> Any:
        raw_length = self.headers.get("Content-Length")
        if raw_length in {None, "", "0"}:
            return None
        return self._read_json()

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_ndjson(self, events: Iterator[dict[str, Any]]) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for event in events:
                encoded = (
                    json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                ).encode("utf-8")
                self.wfile.write(encoded)
                self.wfile.flush()
        except (
            BrainError,
            ComputerToolError,
            BrokenPipeError,
            ConnectionResetError,
            OSError,
        ) as exc:
            if isinstance(exc, (BrainError, ComputerToolError)):
                encoded = (
                    json.dumps(
                        {"type": "error", "error": str(exc)},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
                try:
                    self.wfile.write(encoded)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

    def _json_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _send_audio(self, result: AudioResult, *, synthesis_ms: int | None = None) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", result.content_type)
        self.send_header("Content-Length", str(len(result.data)))
        if synthesis_ms is not None:
            self.send_header("Server-Timing", f"tts;dur={max(0, synthesis_ms)}")
        self.end_headers()
        self.wfile.write(result.data)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self._json_error(HTTPStatus.NOT_FOUND, "文件不存在")
            return
        data = path.read_bytes()
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    application: JarvisApplication | None = None,
) -> JarvisHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("JARVIS 目前只允许绑定本机回环地址")
    return JarvisHTTPServer(
        (host, port), JarvisRequestHandler, application or JarvisApplication()
    )
