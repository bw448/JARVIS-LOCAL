from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when user-facing configuration is invalid."""


SETTINGS_VERSION = 7
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


@dataclass
class IdentityConfig:
    assistant_name: str = "JARVIS"
    owner_name: str = "先生"
    personality: str = "冷静、可靠、简洁，在需要时主动提醒风险。"


@dataclass
class BrainConfig:
    provider: str = "openai_compatible"
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "local-model"
    temperature: float = 0.7
    timeout_seconds: int = 120


@dataclass
class DeepSeekHarnessConfig:
    """Configuration for DeepSeek Harness integration.
    
    When enabled, JARVIS uses DeepSeek Harness as the primary brain,
    providing access to the plugin-based agent architecture.
    Falls back to OpenAI-compatible brain if DSH is unavailable.
    """
    
    # Enable DeepSeek Harness by default
    enabled: bool = True
    
    # Model settings
    model: str = "deepseek-chat"
    provider: str = "deepseek-official"
    max_tokens: Optional[int] = None
    
    # Runtime settings (empty = use bundled runtime)
    runtime_bin: str = ""
    session_root: str = ""
    cordis_config: str = ""
    
    # Connection settings (empty = use brain.base_url/api_key)
    base_url: str = ""
    api_key: str = ""
    
    # Advanced settings
    request_timeout: float = 180.0
    shutdown_timeout: float = 5.0
    fallback_to_openai: bool = True  # Auto-fallback if DSH fails
    
    # Environment overrides
    env_overrides: Dict[str, str] = field(default_factory=dict)


@dataclass
class TTSConfig:
    provider: str = DEFAULT_TTS_PROVIDER
    voice: str = DEFAULT_TTS_VOICE
    speed: float = 1.0
    model_dir: str = ""
    speaker_id: int = DEFAULT_TTS_SPEAKER_ID
    num_threads: int = 2
    external_url: str = ""
    instructions: str = "自然、温和、有陪伴感，像可信赖的私人助理，避免夸张表演。"
    browser_fallback: bool = True
    auto_speak: bool = True


@dataclass
class STTConfig:
    provider: str = "faster_whisper"
    model: str = "small"
    device: str = "cpu"
    language: str = "zh"
    external_url: str = ""
    auto_send_transcript: bool = False
    recording_seconds: int = 45


@dataclass
class PrivacyConfig:
    save_conversations: bool = False
    diagnostic_logging: bool = False


@dataclass
class AppearanceConfig:
    theme: str = "cyan"
    panel_opacity: float = 0.68
    floating_opacity: float = 0.85
    floating_window: bool = True


@dataclass
class InteractionConfig:
    voice_mode_auto_start: bool = False
    proactive_speech: bool = True
    silence_seconds: float = 0.8
    streaming_responses: bool = True
    prewarm_models: bool = True
    computer_control_enabled: bool = False


@dataclass
class Settings:
    version: int = SETTINGS_VERSION
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    brain: BrainConfig = field(default_factory=BrainConfig)
    dsh: DeepSeekHarnessConfig = field(default_factory=DeepSeekHarnessConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    appearance: AppearanceConfig = field(default_factory=AppearanceConfig)
    interaction: InteractionConfig = field(default_factory=InteractionConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def system_prompt(self) -> str:
        """Generate system prompt from identity config."""
        return f"""你是{self.identity.assistant_name}，{self.identity.owner_name}的私人智能助手。
性格特点：{self.identity.personality}
请用中文回复，保持简洁专业。"""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Settings":
        identity_raw = raw.get("identity") or {}
        brain_raw = raw.get("brain") or {}
        dsh_raw = raw.get("dsh") or {}
        tts_raw = raw.get("tts") or {}
        stt_raw = raw.get("stt") or {}
        appearance_raw = raw.get("appearance") or {}
        interaction_raw = raw.get("interaction") or {}
        privacy_raw = raw.get("privacy") or {}

        if not all(isinstance(item, Mapping) for item in (
            identity_raw, brain_raw, dsh_raw, tts_raw, stt_raw,
            appearance_raw, interaction_raw, privacy_raw,
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
        if tts_provider not in {"sherpa_kokoro", "sherpa_onnx", "kokoro", "system", "external"}:
            raise ConfigError("不支持的语音合成提供商")

        stt_provider = str(stt_raw.get("provider", "faster_whisper"))
        if stt_provider not in {"faster_whisper", "sensevoice", "disabled"}:
            raise ConfigError("不支持的语音识别提供商")

        stt_device = str(stt_raw.get("device", "cpu"))
        if stt_device not in {"cpu", "cuda", "auto"}:
            raise ConfigError("语音识别设备必须是 cpu、cuda 或 auto")

        theme = str(appearance_raw.get("theme", "cyan"))
        if theme not in {"cyan", "violet", "emerald", "amber"}:
            theme = "cyan"

        return cls(
            version=SETTINGS_VERSION,
            identity=IdentityConfig(
                assistant_name=_clean_text(identity_raw.get("assistant_name", "JARVIS"), "智能体名字", maximum=40),
                owner_name=_clean_text(identity_raw.get("owner_name", "先生"), "主人称呼", maximum=40),
                personality=_clean_text(identity_raw.get("personality", IdentityConfig().personality), "性格描述", maximum=500),
            ),
            brain=BrainConfig(
                provider=brain_provider,
                base_url=_http_url(brain_raw.get("base_url", "http://127.0.0.1:8080/v1"), "模型接口地址"),
                model=_clean_text(brain_raw.get("model", "local-model"), "模型名称", maximum=160),
                temperature=_number(brain_raw.get("temperature", 0.7), "温度", minimum=0, maximum=2),
                timeout_seconds=int(_number(brain_raw.get("timeout_seconds", 120), "请求超时", minimum=10, maximum=600)),
            ),
            dsh=DeepSeekHarnessConfig(
                enabled=bool(dsh_raw.get("enabled", False)),
                model=_clean_text(dsh_raw.get("model", "deepseek-chat"), "DeepSeek模型", maximum=160),
                provider=_clean_text(dsh_raw.get("provider", "deepseek-official"), "DeepSeek提供商", maximum=100),
                max_tokens=_integer(dsh_raw.get("max_tokens", 0), "最大token数", minimum=0, maximum=1000000) if dsh_raw.get("max_tokens") else None,
                runtime_bin=_clean_text(dsh_raw.get("runtime_bin", ""), "自定义运行时路径", maximum=1000, allow_empty=True),
                session_root=_clean_text(dsh_raw.get("session_root", ""), "会话存储路径", maximum=1000, allow_empty=True),
                cordis_config=_clean_text(dsh_raw.get("cordis_config", ""), "Cordis配置路径", maximum=1000, allow_empty=True),
                base_url=_http_url(dsh_raw.get("base_url", ""), "DeepSeek基础URL", allow_empty=True),
                api_key=_clean_text(dsh_raw.get("api_key", ""), "DeepSeek API密钥", maximum=200, allow_empty=True),
                request_timeout=_number(dsh_raw.get("request_timeout", 120.0), "请求超时", minimum=10, maximum=600),
                shutdown_timeout=_number(dsh_raw.get("shutdown_timeout", 2.0), "关闭超时", minimum=0.5, maximum=30),
            ),
            tts=TTSConfig(
                provider=tts_provider,
                voice=_clean_text(tts_raw.get("voice", DEFAULT_TTS_VOICE), "音色", maximum=120),
                speed=_number(tts_raw.get("speed", 1.0), "语速", minimum=0.5, maximum=2.0),
                model_dir=_clean_text(tts_raw.get("model_dir", ""), "本地语音模型目录", maximum=1000, allow_empty=True),
                speaker_id=_integer(tts_raw.get("speaker_id", DEFAULT_TTS_SPEAKER_ID), "说话人编号", minimum=0, maximum=100000),
                num_threads=_integer(tts_raw.get("num_threads", 2), "语音线程数", minimum=1, maximum=32),
                external_url=_http_url(tts_raw.get("external_url", ""), "外部语音服务地址", allow_empty=True),
                instructions=_clean_text(tts_raw.get("instructions", TTSConfig().instructions), "语音风格指令", maximum=300, allow_empty=True),
                browser_fallback=bool(tts_raw.get("browser_fallback", True)),
                auto_speak=bool(tts_raw.get("auto_speak", True)),
            ),
            stt=STTConfig(
                provider=stt_provider,
                model=_clean_text(stt_raw.get("model", "small"), "语音识别模型", maximum=120),
                device=stt_device,
                language=_clean_text(stt_raw.get("language", "zh"), "识别语言", maximum=20),
                external_url=_http_url(stt_raw.get("external_url", ""), "SenseVoice 服务地址", allow_empty=True),
                auto_send_transcript=bool(stt_raw.get("auto_send_transcript", False)),
                recording_seconds=_integer(stt_raw.get("recording_seconds", 45), "最长录音时间", minimum=5, maximum=120),
            ),
            appearance=AppearanceConfig(
                theme=theme,
                panel_opacity=_number(appearance_raw.get("panel_opacity", 0.68), "面板透明度", minimum=0.3, maximum=1.0),
                floating_opacity=_number(appearance_raw.get("floating_opacity", 0.85), "悬浮窗透明度", minimum=0.3, maximum=1.0),
                floating_window=bool(appearance_raw.get("floating_window", True)),
            ),
            interaction=InteractionConfig(
                voice_mode_auto_start=bool(interaction_raw.get("voice_mode_auto_start", False)),
                proactive_speech=bool(interaction_raw.get("proactive_speech", True)),
                silence_seconds=_number(interaction_raw.get("silence_seconds", 0.8), "静音检测", minimum=0.3, maximum=5.0),
                streaming_responses=bool(interaction_raw.get("streaming_responses", True)),
                prewarm_models=bool(interaction_raw.get("prewarm_models", True)),
                computer_control_enabled=bool(interaction_raw.get("computer_control_enabled", False)),
            ),
            privacy=PrivacyConfig(
                save_conversations=bool(privacy_raw.get("save_conversations", False)),
                diagnostic_logging=bool(privacy_raw.get("diagnostic_logging", False)),
            ),
        )


def default_data_dir() -> Path:
    """Return the default data directory for JARVIS."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", tempfile.gettempdir()))
    else:
        base = Path.home() / ".local" / "share"
    return base / "jarvis"


class SettingsStore:
    """Manages loading and saving of JARVIS settings."""
    
    def __init__(self, path: Optional[Path] = None):
        self._path = path or default_data_dir() / "settings.json"
    
    def load(self) -> Settings:
        """Load settings from file, or return defaults."""
        if not self._path.exists():
            return Settings()
        
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return Settings.from_mapping(data)
        except (json.JSONDecodeError, ConfigError, OSError):
            return Settings()
    
    def save(self, settings: Settings) -> None:
        """Save settings to file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
