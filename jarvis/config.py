from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when user-facing configuration is invalid."""


SETTINGS_VERSION = 4
DEFAULT_TTS_PROVIDER = "sherpa_kokoro"
DEFAULT_TTS_VOICE = "zf_xiaoxiao"
DEFAULT_TTS_SPEAKER_ID = 47


def _clean_text(value: Any, label: str, *, maximum: int, allow_empty: bool = False) -> str:
    text = str(value or "").strip()
    if not text and not allow_empty:
        raise ConfigError(f"{label}不能为空")
    if len(text) > maximum:
        raise ConfigError(f"{label}不能超过 {maximum} 个字符")
    return text


def _number(value: Any, label: str, *, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label}必须是数字") from exc
    if not minimum <= number <= maximum:
        raise ConfigError(f"{label}必须在 {minimum} 到 {maximum} 之间")
    return number


def _integer(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    number = _number(value, label, minimum=minimum, maximum=maximum)
    if not number.is_integer():
        raise ConfigError(f"{label}必须是整数")
    return int(number)


def _http_url(value: Any, label: str, *, allow_empty: bool = False) -> str:
    text = _clean_text(value, label, maximum=500, allow_empty=allow_empty)
    if not text and allow_empty:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{label}必须是 http:// 或 https:// 地址")
    return text.rstrip("/")


@dataclass(slots=True)
class IdentityConfig:
    assistant_name: str = "JARVIS"
    owner_name: str = "先生"
    personality: str = "冷静、可靠、简洁，在需要时主动提醒风险。"


@dataclass(slots=True)
class BrainConfig:
    provider: str = "openai_compatible"
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "local-model"
    temperature: float = 0.7
    timeout_seconds: int = 120


@dataclass(slots=True)
class TTSConfig:
    provider: str = DEFAULT_TTS_PROVIDER
    voice: str = DEFAULT_TTS_VOICE
    speed: float = 1.0
    model_dir: str = ""
    speaker_id: int = DEFAULT_TTS_SPEAKER_ID
    num_threads: int = 2
    external_url: str = ""
    browser_fallback: bool = True
    auto_speak: bool = True


@dataclass(slots=True)
class STTConfig:
    provider: str = "faster_whisper"
    model: str = "small"
    device: str = "cpu"
    language: str = "zh"
    auto_send_transcript: bool = False
    recording_seconds: int = 45


@dataclass(slots=True)
class PrivacyConfig:
    save_conversations: bool = False
    diagnostic_logging: bool = False


@dataclass(slots=True)
class AppearanceConfig:
    theme: str = "cyan"
    panel_opacity: float = 0.68
    floating_opacity: float = 0.85
    floating_window: bool = True


@dataclass(slots=True)
class InteractionConfig:
    voice_mode_auto_start: bool = False
    proactive_speech: bool = True
    silence_seconds: float = 1.2


@dataclass(slots=True)
class Settings:
    version: int = SETTINGS_VERSION
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    brain: BrainConfig = field(default_factory=BrainConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    appearance: AppearanceConfig = field(default_factory=AppearanceConfig)
    interaction: InteractionConfig = field(default_factory=InteractionConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Settings":
        identity_raw = raw.get("identity") or {}
        brain_raw = raw.get("brain") or {}
        tts_raw = raw.get("tts") or {}
        stt_raw = raw.get("stt") or {}
        appearance_raw = raw.get("appearance") or {}
        interaction_raw = raw.get("interaction") or {}
        privacy_raw = raw.get("privacy") or {}

        if not all(isinstance(item, Mapping) for item in (
            identity_raw,
            brain_raw,
            tts_raw,
            stt_raw,
            appearance_raw,
            interaction_raw,
            privacy_raw,
        )):
            raise ConfigError("配置结构无效")

        try:
            raw_version = int(raw.get("version", 1))
        except (TypeError, ValueError):
            raw_version = 1

        brain_provider = str(brain_raw.get("provider", "openai_compatible"))
        if brain_provider not in {"openai_compatible", "disabled"}:
            raise ConfigError("不支持的大脑提供商")

        tts_provider = str(tts_raw.get("provider", DEFAULT_TTS_PROVIDER))
        legacy_sherpa_defaults = (
            raw_version <= 2
            and tts_provider == "sherpa_onnx"
            and not str(tts_raw.get("model_dir", "")).strip()
            and str(tts_raw.get("voice", DEFAULT_TTS_VOICE)) == DEFAULT_TTS_VOICE
            and str(tts_raw.get("speaker_id", 0)) in {"0", "0.0"}
        )
        if legacy_sherpa_defaults:
            tts_provider = DEFAULT_TTS_PROVIDER
        if tts_provider not in {
            "sherpa_kokoro",
            "sherpa_onnx",
            "kokoro",
            "system",
            "external",
        }:
            raise ConfigError("不支持的语音合成提供商")

        default_speaker_id = (
            DEFAULT_TTS_SPEAKER_ID if tts_provider == "sherpa_kokoro" else 0
        )

        stt_provider = str(stt_raw.get("provider", "faster_whisper"))
        if stt_provider not in {"faster_whisper", "disabled"}:
            raise ConfigError("不支持的语音识别提供商")

        stt_device = str(stt_raw.get("device", "cpu"))
        if stt_device not in {"cpu", "cuda", "auto"}:
            raise ConfigError("语音识别设备必须是 cpu、cuda 或 auto")

        theme = str(appearance_raw.get("theme", "cyan"))
        if theme not in {"cyan", "violet", "emerald", "amber"}:
            raise ConfigError("界面配色无效")

        return cls(
            version=SETTINGS_VERSION,
            identity=IdentityConfig(
                assistant_name=_clean_text(
                    identity_raw.get("assistant_name", "JARVIS"), "智能体名字", maximum=40
                ),
                owner_name=_clean_text(
                    identity_raw.get("owner_name", "先生"), "主人称呼", maximum=40
                ),
                personality=_clean_text(
                    identity_raw.get("personality", IdentityConfig().personality),
                    "性格描述",
                    maximum=500,
                ),
            ),
            brain=BrainConfig(
                provider=brain_provider,
                base_url=_http_url(
                    brain_raw.get("base_url", "http://127.0.0.1:8080/v1"),
                    "模型接口地址",
                ),
                model=_clean_text(
                    brain_raw.get("model", "local-model"), "模型名称", maximum=160
                ),
                temperature=_number(
                    brain_raw.get("temperature", 0.7),
                    "温度",
                    minimum=0,
                    maximum=2,
                ),
                timeout_seconds=int(
                    _number(
                        brain_raw.get("timeout_seconds", 120),
                        "请求超时",
                        minimum=10,
                        maximum=600,
                    )
                ),
            ),
            tts=TTSConfig(
                provider=tts_provider,
                voice=_clean_text(
                    tts_raw.get("voice", DEFAULT_TTS_VOICE), "音色", maximum=120
                ),
                speed=_number(
                    tts_raw.get("speed", 1.0), "语速", minimum=0.5, maximum=2.0
                ),
                model_dir=_clean_text(
                    tts_raw.get("model_dir", ""),
                    "本地语音模型目录",
                    maximum=1000,
                    allow_empty=True,
                ),
                speaker_id=_integer(
                    default_speaker_id
                    if legacy_sherpa_defaults
                    else tts_raw.get("speaker_id", default_speaker_id),
                    "说话人编号",
                    minimum=0,
                    maximum=100_000,
                ),
                num_threads=_integer(
                    tts_raw.get("num_threads", 2),
                    "语音线程数",
                    minimum=1,
                    maximum=32,
                ),
                external_url=_http_url(
                    tts_raw.get("external_url", ""),
                    "外部语音服务地址",
                    allow_empty=True,
                ),
                browser_fallback=bool(tts_raw.get("browser_fallback", True)),
                auto_speak=bool(tts_raw.get("auto_speak", True)),
            ),
            stt=STTConfig(
                provider=stt_provider,
                model=_clean_text(
                    stt_raw.get("model", "small"), "语音识别模型", maximum=120
                ),
                device=stt_device,
                language=_clean_text(
                    stt_raw.get("language", "zh"), "识别语言", maximum=20
                ),
                auto_send_transcript=bool(
                    stt_raw.get("auto_send_transcript", False)
                ),
                recording_seconds=_integer(
                    stt_raw.get("recording_seconds", 45),
                    "最长录音时间",
                    minimum=5,
                    maximum=120,
                ),
            ),
            appearance=AppearanceConfig(
                theme=theme,
                panel_opacity=_number(
                    appearance_raw.get("panel_opacity", 0.68),
                    "面板透明度",
                    minimum=0.30,
                    maximum=0.96,
                ),
                floating_opacity=_number(
                    appearance_raw.get("floating_opacity", 0.85),
                    "悬浮窗透明度",
                    minimum=0.25,
                    maximum=1.0,
                ),
                floating_window=bool(
                    appearance_raw.get("floating_window", True)
                ),
            ),
            interaction=InteractionConfig(
                voice_mode_auto_start=bool(
                    interaction_raw.get("voice_mode_auto_start", False)
                ),
                proactive_speech=bool(
                    interaction_raw.get("proactive_speech", True)
                ),
                silence_seconds=_number(
                    interaction_raw.get("silence_seconds", 1.2),
                    "语音停顿时间",
                    minimum=0.6,
                    maximum=3.0,
                ),
            ),
            privacy=PrivacyConfig(
                save_conversations=bool(privacy_raw.get("save_conversations", False)),
                diagnostic_logging=bool(privacy_raw.get("diagnostic_logging", False)),
            ),
        )

    def system_prompt(self) -> str:
        return (
            f"你是 {self.identity.assistant_name}，{self.identity.owner_name} 的私人智能助手。"
            f"你的风格是：{self.identity.personality} "
            f"始终称呼用户为“{self.identity.owner_name}”。"
            "不要声称自己执行了尚未执行的操作；涉及删除、付款或发送消息时先确认。"
        )


def default_data_dir() -> Path:
    override = os.environ.get("JARVIS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "JarvisAssistant"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "JarvisAssistant"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "jarvis-assistant"


class SettingsStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.path = self.data_dir / "settings.json"

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"无法读取设置：{exc}") from exc
        if not isinstance(raw, Mapping):
            raise ConfigError("设置文件必须是 JSON 对象")
        return Settings.from_mapping(raw)

    def save(self, settings: Settings) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="settings-", suffix=".tmp", dir=self.data_dir
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
