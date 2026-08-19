from __future__ import annotations

import argparse
import io
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


MAX_JSON_BYTES = 1024 * 1024


class QwenRuntime:
    def __init__(self, model_path: str, device: str, dtype_name: str) -> None:
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise RuntimeError(
                "缺少 Qwen3-TTS 运行依赖，请在独立环境安装 qwen-tts、torch 和 soundfile"
            ) from exc

        dtype = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }[dtype_name]
        self.model_name = model_path
        self.model = Qwen3TTSModel.from_pretrained(
            model_path,
            device_map=device,
            dtype=dtype,
        )
        self.lock = threading.Lock()

    def synthesize(self, text: str, voice: str, instructions: str) -> bytes:
        try:
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("缺少 soundfile，无法输出 WAV") from exc

        with self.lock:
            wavs, sample_rate = self.model.generate_custom_voice(
                text=text,
                language="Auto",
                speaker=voice,
                instruct=instructions,
            )
        if not wavs:
            raise RuntimeError("Qwen3-TTS 没有生成音频")
        output = io.BytesIO()
        sf.write(output, wavs[0], sample_rate, format="WAV", subtype="PCM_16")
        return output.getvalue()


class VoiceServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], runtime: QwenRuntime) -> None:
        self.runtime = runtime
        super().__init__(address, VoiceHandler)


class VoiceHandler(BaseHTTPRequestHandler):
    server_version = "JarvisQwen3TTSWorker/1.0"

    @property
    def runtime(self) -> QwenRuntime:
        server = self.server
        assert isinstance(server, VoiceServer)
        return server.runtime

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[QWEN3-TTS] {self.address_string()} {format_string % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(
                {
                    "status": "ready",
                    "engine": "qwen3-tts",
                    "model": self.runtime.model_name,
                }
            )
            return
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/audio/speech":
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json()
            text = str(payload.get("input", "")).strip()
            voice = str(payload.get("voice", "Vivian")).strip() or "Vivian"
            instructions = str(payload.get("instructions", "")).strip()
            if not text:
                raise ValueError("input 不能为空")
            if len(text) > 4000:
                raise ValueError("input 不能超过 4000 个字符")
            wav = self.runtime.synthesize(text, voice, instructions)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(wav)
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            print(f"[QWEN3-TTS] internal error: {type(exc).__name__}: {exc}")
            self._json({"error": "语音合成内部错误"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type != "application/json":
            raise ValueError("只接受 application/json")
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_JSON_BYTES:
            raise ValueError("请求大小无效")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("JSON 必须是对象")
        return payload

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS Qwen3-TTS local worker")
    parser.add_argument("--model", required=True, help="本地 CustomVoice 模型目录")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9880)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--dtype",
        choices=("float32", "float16", "bfloat16"),
        default="bfloat16",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("工作进程只允许绑定本机回环地址")
    runtime = QwenRuntime(args.model, args.device, args.dtype)
    server = VoiceServer((args.host, args.port), runtime)
    print(f"Qwen3-TTS worker ready: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
