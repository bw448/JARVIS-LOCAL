from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib import error, request

from .config import DEFAULT_TTS_PROVIDER, Settings, default_data_dir
from .runtime import bundled_path


class SpeechError(RuntimeError):
    pass


@dataclass(slots=True)
class AudioResult:
    data: bytes
    content_type: str = "audio/wav"


@dataclass(frozen=True, slots=True)
class SherpaModelFiles:
    root: Path
    family: str
    model: Path
    tokens: Path
    voices: Path | None
    lexicons: tuple[Path, ...]
    data_dir: Path | None
    rule_fsts: tuple[Path, ...]
    license_file: Path | None

    @property
    def display_name(self) -> str:
        return self.root.name


KOKORO_VOICE_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "voice": "zf_xiaoxiao",
        "speaker_id": 47,
        "label": "晓晓 · 甜美女声",
        "description": "甜美自然，默认推荐",
    },
    {
        "voice": "zf_xiaoni",
        "speaker_id": 46,
        "label": "晓妮 · 元气女声",
        "description": "轻快明亮",
    },
    {
        "voice": "zf_xiaoyi",
        "speaker_id": 48,
        "label": "晓伊 · 温柔女声",
        "description": "柔和舒缓",
    },
    {
        "voice": "zf_xiaobei",
        "speaker_id": 45,
        "label": "晓北 · 清亮女声",
        "description": "清晰利落",
    },
)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return name in sys.modules


def default_sherpa_model_dir(provider: str = DEFAULT_TTS_PROVIDER) -> Path:
    folder = (
        "kokoro-multi-lang-v1_0"
        if provider == "sherpa_kokoro"
        else "vits-melo-tts-zh_en"
    )
    bundled = bundled_path("models", "tts", folder)
    if bundled is not None and bundled.is_dir():
        return bundled
    return default_data_dir() / "models" / "tts" / folder


def resolve_whisper_model(model: str) -> str:
    cleaned = str(model or "small").strip() or "small"
    if cleaned == "small":
        bundled = bundled_path("models", "stt", "faster-whisper-small")
        if bundled is not None and bundled.is_dir():
            return str(bundled)
    return cleaned


_ESPEAK_REQUIRED_FILES = ("phontab", "phondata", "phonindex", "intonations")


def _is_ascii_path(path: Path) -> bool:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _windows_short_path(path: Path) -> Path | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        get_short_path = ctypes.windll.kernel32.GetShortPathNameW
        get_short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        get_short_path.restype = ctypes.c_uint
        size = get_short_path(str(path), None, 0)
        if not size:
            return None
        buffer = ctypes.create_unicode_buffer(size)
        if not get_short_path(str(path), buffer, size):
            return None
        candidate = Path(buffer.value)
        return candidate if _is_ascii_path(candidate) else None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _espeak_data_is_complete(path: Path) -> bool:
    return path.is_dir() and all((path / name).is_file() for name in _ESPEAK_REQUIRED_FILES)


def _espeak_data_signature(path: Path) -> str:
    digest = hashlib.sha256()
    for name in _ESPEAK_REQUIRED_FILES:
        digest.update(name.encode("ascii"))
        with (path / name).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()[:16]


def _copy_espeak_data(source: Path, cache_root: Path, signature: str) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / signature
    if _espeak_data_is_complete(target):
        return target

    stage = Path(tempfile.mkdtemp(prefix=f".{signature}-", dir=cache_root))
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True)
        if not _espeak_data_is_complete(stage):
            raise OSError("copied eSpeak data is incomplete")
        if target.exists():
            shutil.rmtree(target)
        os.replace(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
    return target


def prepare_espeak_data_dir(path: Path) -> Path:
    """Return an eSpeak data path safe for sherpa-onnx on Windows.

    The Windows eSpeak runtime bundled by sherpa-onnx reads ESPEAK_DATA_PATH
    through a narrow-character API. A Unicode installation path can therefore
    terminate the native process before Python can report an exception.
    """

    if not _espeak_data_is_complete(path):
        raise SpeechError(f"eSpeak 离线数据不完整：{path}")
    if os.name != "nt":
        return path

    direct = path if _is_ascii_path(path) else _windows_short_path(path)
    if direct is not None:
        os.environ["ESPEAK_DATA_PATH"] = str(direct)
        return direct

    signature = _espeak_data_signature(path)
    candidates = [default_data_dir() / "runtime" / "espeak"]
    system_drive = os.environ.get("SystemDrive", "C:").rstrip("\\/") or "C:"
    candidates.append(
        Path(f"{system_drive}\\Users\\Public\\JARVIS-LOCAL\\runtime\\espeak")
    )
    errors: list[str] = []
    for cache_root in candidates:
        try:
            cached = _copy_espeak_data(path, cache_root, signature)
            safe = cached if _is_ascii_path(cached) else _windows_short_path(cached)
            if safe is None:
                errors.append(f"{cache_root}: 路径仍包含非 ASCII 字符")
                continue
            os.environ["ESPEAK_DATA_PATH"] = str(safe)
            return safe
        except OSError as exc:
            errors.append(f"{cache_root}: {exc}")

    detail = "; ".join(errors)
    raise SpeechError(f"无法准备 Windows eSpeak 兼容目录：{detail}")


def _candidate_model_roots(root: Path) -> Iterable[Path]:
    yield root
    try:
        children = sorted(path for path in root.iterdir() if path.is_dir())
    except OSError:
        return
    yield from children


def locate_sherpa_model(settings: Settings) -> SherpaModelFiles | None:
    configured = os.path.expandvars(settings.tts.model_dir).strip()
    root = (
        Path(configured).expanduser()
        if configured
        else default_sherpa_model_dir(settings.tts.provider)
    )
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        return None

    for candidate in _candidate_model_roots(root):
        tokens = candidate / "tokens.txt"
        if not tokens.is_file():
            continue

        preferred_models = (candidate / "model.onnx", candidate / "model.int8.onnx")
        model = next((path for path in preferred_models if path.is_file()), None)
        if model is None:
            try:
                onnx_files = sorted(
                    path
                    for path in candidate.glob("*.onnx")
                    if not any(word in path.name.lower() for word in ("vocoder", "encoder", "decoder"))
                )
            except OSError:
                onnx_files = []
            if len(onnx_files) != 1:
                continue
            model = onnx_files[0]

        voices = candidate / "voices.bin"
        family = "kokoro" if voices.is_file() else "vits"
        expected_family = (
            "kokoro" if settings.tts.provider == "sherpa_kokoro" else "vits"
        )
        if family != expected_family:
            continue

        if family == "kokoro":
            lexicons = tuple(
                path
                for name in ("lexicon-us-en.txt", "lexicon-zh.txt")
                if (path := candidate / name).is_file()
            )
            data_candidates = (candidate / "espeak-ng-data", candidate / "dict")
            rule_names = ("phone-zh.fst", "date-zh.fst", "number-zh.fst")
        else:
            lexicon = candidate / "lexicon.txt"
            lexicons = (lexicon,) if lexicon.is_file() else ()
            data_candidates = (candidate / "dict", candidate / "espeak-ng-data")
            rule_names = (
                "phone.fst",
                "date.fst",
                "number.fst",
                "new_heteronym.fst",
            )

        data_dir = next((path for path in data_candidates if path.is_dir()), None)
        rule_fsts = tuple(
            path
            for name in rule_names
            if (path := candidate / name).is_file()
        )
        license_file = next(
            (
                path
                for name in ("LICENSE", "LICENSE.txt", "MODEL_CARD", "MODEL_CARD.md")
                if (path := candidate / name).is_file()
            ),
            None,
        )
        return SherpaModelFiles(
            root=candidate,
            family=family,
            model=model,
            tokens=tokens,
            voices=voices if voices.is_file() else None,
            lexicons=lexicons,
            data_dir=data_dir,
            rule_fsts=rule_fsts,
            license_file=license_file,
        )
    return None


def _pcm16_wav(samples: Iterable[float], sample_rate: int) -> bytes:
    if not 8_000 <= int(sample_rate) <= 192_000:
        raise SpeechError("语音模型返回了无效采样率")
    pcm = array("h")
    for sample in samples:
        value = float(sample)
        if not math.isfinite(value):
            value = 0.0
        value = max(-1.0, min(1.0, value))
        pcm.append(max(-32_768, min(32_767, round(value * 32_767))))
    if not pcm:
        raise SpeechError("本地语音模型没有生成音频")
    if sys.byteorder != "little":
        pcm.byteswap()
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())
    return output.getvalue()


class SpeechService:
    MAX_AUDIO_BYTES = 25 * 1024 * 1024
    MAX_TTS_BYTES = 20 * 1024 * 1024

    def __init__(self) -> None:
        self._kokoro_pipeline: Any = None
        self._kokoro_lock = threading.Lock()
        self._sherpa_engines: dict[tuple[Any, ...], Any] = {}
        self._sherpa_lock = threading.Lock()
        self._whisper_models: dict[tuple[str, str], Any] = {}
        self._whisper_lock = threading.Lock()

    def clear_tts_cache(self) -> None:
        with self._sherpa_lock:
            self._sherpa_engines.clear()
        with self._kokoro_lock:
            self._kokoro_pipeline = None

    def capabilities(self, settings: Settings) -> dict[str, Any]:
        sherpa_installed = _module_available("sherpa_onnx")
        sherpa_provider = settings.tts.provider in {"sherpa_kokoro", "sherpa_onnx"}
        sherpa_model = locate_sherpa_model(settings) if sherpa_provider else None
        kokoro_installed = _module_available("kokoro")
        whisper_installed = _module_available("faster_whisper")

        tts_ready = {
            "system": True,
            "sherpa_kokoro": sherpa_installed and sherpa_model is not None,
            "sherpa_onnx": sherpa_installed and sherpa_model is not None,
            "kokoro": kokoro_installed,
            "external": bool(settings.tts.external_url),
        }.get(settings.tts.provider, False)
        if tts_ready:
            tts_reason = "ready"
        elif sherpa_provider and not sherpa_installed:
            tts_reason = "sherpa_package_missing"
        elif sherpa_provider:
            tts_reason = "sherpa_model_missing"
        elif settings.tts.provider == "kokoro":
            tts_reason = "kokoro_package_missing"
        elif settings.tts.provider == "external":
            tts_reason = "external_url_missing"
        else:
            tts_reason = "provider_unavailable"

        return {
            "tts": {
                "provider": settings.tts.provider,
                "ready": tts_ready,
                "reason": tts_reason,
                "sherpa_onnx_installed": sherpa_installed,
                "sherpa_model_found": sherpa_model is not None,
                "sherpa_model_name": sherpa_model.display_name if sherpa_model else "",
                "sherpa_model_family": sherpa_model.family if sherpa_model else "",
                "sherpa_model_license_found": bool(
                    sherpa_model and sherpa_model.license_file
                ),
                "voice": settings.tts.voice,
                "speaker_id": settings.tts.speaker_id,
                "voice_presets": [dict(preset) for preset in KOKORO_VOICE_PRESETS],
                "kokoro_installed": kokoro_installed,
                "browser_fallback": settings.tts.browser_fallback,
            },
            "stt": {
                "provider": settings.stt.provider,
                "ready": settings.stt.provider == "disabled" or whisper_installed,
                "faster_whisper_installed": whisper_installed,
            },
        }

    def synthesize(self, settings: Settings, text: str) -> AudioResult | None:
        cleaned = str(text or "").strip()
        if not cleaned:
            raise SpeechError("没有可朗读的文字")
        if len(cleaned) > 4000:
            raise SpeechError("单次朗读不能超过 4000 个字符")

        if settings.tts.provider == "system":
            return None
        try:
            if settings.tts.provider in {"sherpa_kokoro", "sherpa_onnx"}:
                return self._sherpa_tts(settings, cleaned)
            if settings.tts.provider == "kokoro":
                return self._kokoro_tts(settings, cleaned)
            if settings.tts.provider == "external":
                return self._external_tts(settings, cleaned)
            raise SpeechError("不支持的语音合成提供商")
        except SpeechError:
            if settings.tts.browser_fallback:
                return None
            raise

    def _sherpa_tts(self, settings: Settings, text: str) -> AudioResult:
        if not _module_available("sherpa_onnx"):
            raise SpeechError("sherpa-onnx 尚未安装，请运行本地语音安装脚本")
        files = locate_sherpa_model(settings)
        if files is None:
            expected = settings.tts.model_dir or str(
                default_sherpa_model_dir(settings.tts.provider)
            )
            raise SpeechError(f"未找到 sherpa-onnx 语音模型，请检查模型目录：{expected}")

        try:
            import sherpa_onnx
        except ImportError as exc:
            raise SpeechError(f"sherpa-onnx 依赖不完整：{exc}") from exc

        runtime_data_dir = files.data_dir
        if files.family == "kokoro" and files.data_dir is not None:
            runtime_data_dir = prepare_espeak_data_dir(files.data_dir)

        cache_files = (
            files.model,
            files.tokens,
            *((files.voices,) if files.voices else ()),
            *files.lexicons,
            *files.rule_fsts,
        )
        try:
            file_stamps = tuple(path.stat().st_mtime_ns for path in cache_files)
        except OSError as exc:
            raise SpeechError("无法读取本地语音模型") from exc
        key = (
            files.family,
            str(files.model.resolve()),
            file_stamps,
            str(files.voices.resolve()) if files.voices else "",
            tuple(str(path.resolve()) for path in files.lexicons),
            str(runtime_data_dir.resolve()) if runtime_data_dir else "",
            tuple(str(path.resolve()) for path in files.rule_fsts),
            settings.tts.num_threads,
        )

        with self._sherpa_lock:
            engine = self._sherpa_engines.get(key)
            if engine is None:
                try:
                    if files.family == "kokoro":
                        model_config = sherpa_onnx.OfflineTtsModelConfig(
                            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                                model=str(files.model),
                                voices=str(files.voices),
                                tokens=str(files.tokens),
                                lexicon=",".join(
                                    str(path) for path in files.lexicons
                                ),
                                data_dir=str(runtime_data_dir) if runtime_data_dir else "",
                            ),
                            provider="cpu",
                            debug=False,
                            num_threads=settings.tts.num_threads,
                        )
                    else:
                        model_config = sherpa_onnx.OfflineTtsModelConfig(
                            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                                model=str(files.model),
                                tokens=str(files.tokens),
                                lexicon=",".join(
                                    str(path) for path in files.lexicons
                                ),
                                data_dir=str(runtime_data_dir) if runtime_data_dir else "",
                            ),
                            provider="cpu",
                            debug=False,
                            num_threads=settings.tts.num_threads,
                        )
                    config = sherpa_onnx.OfflineTtsConfig(
                        model=model_config,
                        rule_fsts=",".join(str(path) for path in files.rule_fsts),
                        max_num_sentences=2,
                    )
                    if not config.validate():
                        raise SpeechError("本地语音模型文件不完整或格式不兼容")
                    engine = sherpa_onnx.OfflineTts(config)
                except SpeechError:
                    raise
                except Exception as exc:
                    raise SpeechError(f"sherpa-onnx 模型加载失败：{exc}") from exc
                self._sherpa_engines[key] = engine

            try:
                generation = sherpa_onnx.GenerationConfig()
                generation.sid = settings.tts.speaker_id
                generation.speed = settings.tts.speed
                generation.silence_scale = 0.2
                audio = engine.generate(text, generation)
            except Exception as exc:
                raise SpeechError(f"sherpa-onnx 合成失败：{exc}") from exc

        return AudioResult(_pcm16_wav(audio.samples, int(audio.sample_rate)))

    def _kokoro_tts(self, settings: Settings, text: str) -> AudioResult:
        if not _module_available("kokoro"):
            raise SpeechError("Kokoro 尚未安装，请执行可选语音组件安装脚本")
        try:
            import numpy as np
            import soundfile as sf
            from kokoro import KPipeline
        except ImportError as exc:
            raise SpeechError(f"Kokoro 依赖不完整：{exc}") from exc

        with self._kokoro_lock:
            if self._kokoro_pipeline is None:
                self._kokoro_pipeline = KPipeline(lang_code="z")
            try:
                chunks = [
                    np.asarray(audio)
                    for _, _, audio in self._kokoro_pipeline(
                        text,
                        voice=settings.tts.voice,
                        speed=settings.tts.speed,
                        split_pattern=r"\n+",
                    )
                ]
            except Exception as exc:
                raise SpeechError(f"Kokoro 合成失败：{exc}") from exc

        if not chunks:
            raise SpeechError("Kokoro 没有生成音频")
        joined = np.concatenate(chunks)
        output = io.BytesIO()
        sf.write(output, joined, 24_000, format="WAV", subtype="PCM_16")
        return AudioResult(output.getvalue())

    def _external_tts(self, settings: Settings, text: str) -> AudioResult:
        if not settings.tts.external_url:
            raise SpeechError("尚未配置外部语音服务地址")
        payload = {
            "model": "tts-1",
            "voice": settings.tts.voice,
            "input": text,
            "speed": settings.tts.speed,
            "response_format": "wav",
        }
        outgoing = request.Request(
            settings.tts.external_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "audio/*"},
            method="POST",
        )
        try:
            with request.urlopen(outgoing, timeout=120) as response:
                data = response.read(self.MAX_TTS_BYTES + 1)
                content_type = response.headers.get_content_type()
        except error.HTTPError as exc:
            detail = exc.read(1024).decode("utf-8", errors="replace")
            raise SpeechError(f"外部语音服务返回 HTTP {exc.code}：{detail[:240]}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise SpeechError("无法连接外部语音服务") from exc
        if not data:
            raise SpeechError("外部语音服务没有返回音频")
        if len(data) > self.MAX_TTS_BYTES:
            raise SpeechError("外部语音服务返回的音频过大")
        if not (content_type or "").startswith("audio/"):
            raise SpeechError("外部语音服务返回的不是音频")
        return AudioResult(data=data, content_type=content_type)

    def transcribe(self, settings: Settings, audio: bytes, content_type: str) -> str:
        if settings.stt.provider == "disabled":
            raise SpeechError("语音识别已关闭")
        if not audio:
            raise SpeechError("没有收到录音")
        if len(audio) > self.MAX_AUDIO_BYTES:
            raise SpeechError("录音文件过大")
        if not _module_available("faster_whisper"):
            raise SpeechError("faster-whisper 尚未安装，请执行语音组件安装脚本")

        media_type = content_type.split(";", 1)[0].strip().lower()
        suffixes = {
            "audio/webm": ".webm",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".m4a",
            "audio/ogg": ".ogg",
        }
        if media_type not in suffixes:
            raise SpeechError("不支持的录音格式")

        from faster_whisper import WhisperModel

        resolved_model = resolve_whisper_model(settings.stt.model)
        key = (resolved_model, settings.stt.device)
        with self._whisper_lock:
            model = self._whisper_models.get(key)
            if model is None:
                compute_type = {
                    "cuda": "float16",
                    "cpu": "int8",
                    "auto": "default",
                }[settings.stt.device]
                try:
                    model = WhisperModel(
                        resolved_model,
                        device=settings.stt.device,
                        compute_type=compute_type,
                    )
                except Exception as exc:
                    raise SpeechError(f"语音识别模型加载失败：{exc}") from exc
                self._whisper_models[key] = model

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffixes[media_type], delete=False) as temporary:
                temporary.write(audio)
                temporary_path = Path(temporary.name)
            try:
                segments, _ = model.transcribe(
                    str(temporary_path),
                    language=settings.stt.language or None,
                    beam_size=3,
                    vad_filter=True,
                    condition_on_previous_text=False,
                )
                text = "".join(segment.text for segment in segments).strip()
            except Exception as exc:
                raise SpeechError(f"语音识别失败：{exc}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        if not text:
            raise SpeechError("没有识别到清晰语音")
        return text[:20_000]
