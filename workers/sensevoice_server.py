from __future__ import annotations

import argparse
import json
import re
import tempfile
import threading
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MAX_AUDIO_BYTES = 25 * 1024 * 1024
TAG_PATTERN = re.compile(r"<\|([^|]+)\|>")


def parse_multipart(content_type: str, body: bytes) -> tuple[bytes, str, dict[str, str]]:
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii")
        + body
    )
    fields: dict[str, str] = {}
    audio = b""
    filename = "recording.wav"
    if not message.is_multipart():
        raise ValueError("请求必须是 multipart/form-data")
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        if name == "file":
            audio = payload
            filename = part.get_filename() or filename
        else:
            fields[name] = payload.decode("utf-8", errors="replace").strip()
    if not audio:
        raise ValueError("缺少音频文件")
    return audio, filename, fields


class SenseVoiceRuntime:
    def __init__(self, model_path: str, device: str) -> None:
        try:
            from funasr import AutoModel
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
        except ImportError as exc:
            raise RuntimeError("缺少 FunASR/SenseVoice 运行依赖") from exc

        self.model_name = model_path
        self.model = AutoModel(
            model=model_path,
            trust_remote_code=False,
            device=device,
        )
        self.postprocess = rich_transcription_postprocess
        self.lock = threading.Lock()

    def transcribe(self, path: Path, language: str) -> dict[str, str]:
        normalized_language = "auto" if language in {"", "auto"} else language
        with self.lock:
            result = self.model.generate(
                input=str(path),
                cache={},
                language=normalized_language,
                use_itn=True,
                batch_size=1,
            )
        if not result:
            raise RuntimeError("SenseVoice 没有返回结果")
        raw_text = str(result[0].get("text", ""))
        tags = TAG_PATTERN.findall(raw_text)
        text = self.postprocess(raw_text).strip()
        if not text:
            raise RuntimeError("SenseVoice 没有识别到清晰语音")
        known_languages = {"zh", "en", "yue", "ja", "ko"}
        detected_language = next((tag for tag in tags if tag in known_languages), "")
        known_emotions = {
            "HAPPY",
            "SAD",
            "ANGRY",
            "NEUTRAL",
            "FEARFUL",
            "DISGUSTED",
            "SURPRISED",
        }
        emotion = next((tag.lower() for tag in tags if tag in known_emotions), "")
        return {"text": text, "language": detected_language, "emotion": emotion}


class VoiceServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], runtime: SenseVoiceRuntime) -> None:
        self.runtime = runtime
        super().__init__(address, VoiceHandler)


class VoiceHandler(BaseHTTPRequestHandler):
    server_version = "JarvisSenseVoiceWorker/1.0"

    @property
    def runtime(self) -> SenseVoiceRuntime:
        server = self.server
        assert isinstance(server, VoiceServer)
        return server.runtime

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[SENSEVOICE] {self.address_string()} {format_string % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(
                {
                    "status": "ready",
                    "engine": "sensevoice",
                    "model": self.runtime.model_name,
                }
            )
            return
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/audio/transcriptions":
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        temporary_path: Path | None = None
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_AUDIO_BYTES + 1024 * 1024:
                raise ValueError("请求大小无效")
            audio, filename, fields = parse_multipart(
                self.headers.get("Content-Type", ""), self.rfile.read(length)
            )
            if len(audio) > MAX_AUDIO_BYTES:
                raise ValueError("音频文件过大")
            suffix = Path(filename).suffix[:12] or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                temporary.write(audio)
                temporary_path = Path(temporary.name)
            payload = self.runtime.transcribe(
                temporary_path,
                fields.get("language", "auto"),
            )
            self._json(payload)
        except (ValueError, RuntimeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            print(f"[SENSEVOICE] internal error: {type(exc).__name__}: {exc}")
            self._json({"error": "语音识别内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS SenseVoice local worker")
    parser.add_argument("--model", required=True, help="本地 SenseVoiceSmall 模型目录")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50000)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("工作进程只允许绑定本机回环地址")
    runtime = SenseVoiceRuntime(args.model, args.device)
    server = VoiceServer((args.host, args.port), runtime)
    print(f"SenseVoice worker ready: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
