from __future__ import annotations

import io
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from jarvis.config import Settings
from jarvis.speech import (
    SpeechService,
    _pcm16_wav,
    default_sherpa_model_dir,
    locate_sherpa_model,
    resolve_whisper_model,
)


def make_vits_model_directory(root: Path) -> Path:
    model_dir = root / "vits-melo-tts-zh_en"
    model_dir.mkdir()
    (model_dir / "model.onnx").write_bytes(b"fake-onnx")
    (model_dir / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    (model_dir / "lexicon.txt").write_text("test t e s t\n", encoding="utf-8")
    (model_dir / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (model_dir / "dict").mkdir()
    (model_dir / "date.fst").write_bytes(b"fst")
    return model_dir


def make_kokoro_model_directory(root: Path) -> Path:
    model_dir = root / "kokoro-multi-lang-v1_0"
    model_dir.mkdir()
    (model_dir / "model.onnx").write_bytes(b"fake-onnx")
    (model_dir / "voices.bin").write_bytes(b"fake-voices")
    (model_dir / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    (model_dir / "lexicon-us-en.txt").write_text("test t e s t\n", encoding="utf-8")
    (model_dir / "lexicon-zh.txt").write_text("你好 ni hao\n", encoding="utf-8")
    (model_dir / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    espeak_data = model_dir / "espeak-ng-data"
    espeak_data.mkdir()
    for name in ("phontab", "phondata", "phonindex", "intonations"):
        (espeak_data / name).write_bytes(f"fake-{name}".encode("ascii"))
    (model_dir / "number-zh.fst").write_bytes(b"fst")
    return model_dir


class SpeechTests(unittest.TestCase):
    def test_bundled_models_are_preferred_when_present(self) -> None:
        bundled_tts = Path("D:/portable/models/tts/kokoro-multi-lang-v1_0")
        bundled_stt = Path("D:/portable/models/stt/faster-whisper-small")

        def fake_bundled_path(*parts):
            joined = "/".join(parts)
            return bundled_tts if joined.startswith("models/tts/") else bundled_stt

        with patch("jarvis.speech.bundled_path", side_effect=fake_bundled_path), patch.object(
            Path, "is_dir", return_value=True
        ):
            self.assertEqual(default_sherpa_model_dir(), bundled_tts)
            self.assertEqual(resolve_whisper_model("small"), str(bundled_stt))
            self.assertEqual(resolve_whisper_model("medium"), "medium")

    def test_model_locator_accepts_parent_or_exact_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_dir = make_kokoro_model_directory(root)
            settings = Settings()
            settings.tts.model_dir = str(root)
            files = locate_sherpa_model(settings)
            self.assertIsNotNone(files)
            assert files is not None
            self.assertEqual(files.root, model_dir)
            self.assertEqual(files.family, "kokoro")
            self.assertEqual(files.model.name, "model.onnx")
            self.assertEqual(files.voices.name, "voices.bin")
            self.assertEqual(files.data_dir.name, "espeak-ng-data")
            self.assertEqual(len(files.lexicons), 2)
            self.assertTrue(files.license_file.is_file())

            settings.tts.model_dir = str(model_dir / "model.onnx")
            self.assertEqual(locate_sherpa_model(settings).root, model_dir)

    def test_vits_model_remains_available_as_compatibility_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_dir = make_vits_model_directory(root)
            settings = Settings()
            settings.tts.provider = "sherpa_onnx"
            settings.tts.model_dir = str(model_dir)
            files = locate_sherpa_model(settings)
            self.assertIsNotNone(files)
            self.assertEqual(files.family, "vits")
            self.assertIsNone(files.voices)

    def test_pcm_converter_produces_valid_mono_wav(self) -> None:
        data = _pcm16_wav([-1.2, -0.5, 0.0, 0.5, 1.2], 24_000)
        with wave.open(io.BytesIO(data), "rb") as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getframerate(), 24_000)
            self.assertEqual(wav.getnframes(), 5)

    def test_capability_reason_distinguishes_missing_model(self) -> None:
        service = SpeechService()
        with patch(
            "jarvis.speech._module_available",
            side_effect=lambda name: name == "sherpa_onnx",
        ), patch("jarvis.speech.locate_sherpa_model", return_value=None):
            capability = service.capabilities(Settings())["tts"]
        self.assertFalse(capability["ready"])
        self.assertEqual(capability["reason"], "sherpa_model_missing")

    def test_sherpa_engine_is_cached_and_returns_wav(self) -> None:
        counters = {"engines": 0}

        class ValueObject:
            def __init__(self, **kwargs):
                self.values = kwargs

        class OfflineTtsConfig(ValueObject):
            def validate(self) -> bool:
                return True

        class GenerationConfig:
            sid = 0
            speed = 1.0
            silence_scale = 0.2

        class OfflineTts:
            def __init__(self, config):
                counters["engines"] += 1
                self.config = config

            def generate(self, text, generation):
                self.last_text = text
                self.last_generation = generation
                counters["speaker_id"] = generation.sid
                return types.SimpleNamespace(
                    samples=[0.0, 0.25, -0.25, 0.0],
                    sample_rate=22_050,
                )

        fake_module = types.ModuleType("sherpa_onnx")
        fake_module.OfflineTtsVitsModelConfig = ValueObject
        fake_module.OfflineTtsKokoroModelConfig = ValueObject
        fake_module.OfflineTtsModelConfig = ValueObject
        fake_module.OfflineTtsConfig = OfflineTtsConfig
        fake_module.GenerationConfig = GenerationConfig
        fake_module.OfflineTts = OfflineTts

        with tempfile.TemporaryDirectory() as directory:
            model_dir = make_kokoro_model_directory(Path(directory))
            settings = Settings()
            settings.tts.model_dir = str(model_dir)
            settings.tts.browser_fallback = False
            service = SpeechService()
            with patch.dict(sys.modules, {"sherpa_onnx": fake_module}):
                first = service.synthesize(settings, "你好")
                second = service.synthesize(settings, "再次测试")

        self.assertEqual(counters["engines"], 1)
        self.assertEqual(counters["speaker_id"], 47)
        self.assertTrue(first.data.startswith(b"RIFF"))
        self.assertTrue(second.data.startswith(b"RIFF"))


if __name__ == "__main__":
    unittest.main()
