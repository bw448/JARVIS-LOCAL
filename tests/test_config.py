from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jarvis.config import ConfigError, Settings, SettingsStore


class SettingsTests(unittest.TestCase):
    def test_empty_mapping_uses_safe_defaults(self) -> None:
        settings = Settings.from_mapping({})
        self.assertEqual(settings.identity.assistant_name, "JARVIS")
        self.assertEqual(settings.identity.owner_name, "先生")
        self.assertEqual(settings.version, 4)
        self.assertEqual(settings.tts.provider, "sherpa_kokoro")
        self.assertEqual(settings.tts.voice, "zf_xiaoxiao")
        self.assertEqual(settings.tts.speaker_id, 47)
        self.assertEqual(settings.stt.recording_seconds, 45)
        self.assertEqual(settings.appearance.theme, "cyan")
        self.assertEqual(settings.appearance.panel_opacity, 0.68)
        self.assertEqual(settings.appearance.floating_opacity, 0.85)
        self.assertTrue(settings.appearance.floating_window)
        self.assertTrue(settings.interaction.proactive_speech)
        self.assertFalse(settings.interaction.voice_mode_auto_start)
        self.assertFalse(settings.privacy.save_conversations)

    def test_names_are_injected_into_system_prompt(self) -> None:
        raw = Settings().to_dict()
        raw["identity"]["assistant_name"] = "星期五"
        raw["identity"]["owner_name"] = "老板"
        prompt = Settings.from_mapping(raw).system_prompt()
        self.assertIn("星期五", prompt)
        self.assertIn("老板", prompt)

    def test_invalid_remote_protocol_is_rejected(self) -> None:
        raw = Settings().to_dict()
        raw["brain"]["base_url"] = "file:///etc/passwd"
        with self.assertRaises(ConfigError):
            Settings.from_mapping(raw)

    def test_store_does_not_add_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory))
            store.save(Settings())
            payload = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertNotIn("api_key", json.dumps(payload))
            loaded = store.load()
            self.assertEqual(loaded.identity.assistant_name, "JARVIS")

    def test_fractional_integer_settings_are_rejected(self) -> None:
        raw = Settings().to_dict()
        raw["tts"]["speaker_id"] = 1.5
        with self.assertRaises(ConfigError):
            Settings.from_mapping(raw)

    def test_version_one_shape_is_upgraded_with_voice_defaults(self) -> None:
        raw = {
            "version": 1,
            "identity": {"assistant_name": "星期五", "owner_name": "老板"},
        }
        settings = Settings.from_mapping(raw)
        self.assertEqual(settings.version, 4)
        self.assertEqual(settings.identity.assistant_name, "星期五")
        self.assertEqual(settings.tts.provider, "sherpa_kokoro")
        self.assertEqual(settings.tts.speaker_id, 47)
        self.assertFalse(settings.stt.auto_send_transcript)

    def test_invalid_appearance_values_are_rejected(self) -> None:
        raw = Settings().to_dict()
        raw["appearance"]["theme"] = "unknown"
        with self.assertRaises(ConfigError):
            Settings.from_mapping(raw)

        raw = Settings().to_dict()
        raw["appearance"]["panel_opacity"] = 0.2
        with self.assertRaises(ConfigError):
            Settings.from_mapping(raw)

        raw = Settings().to_dict()
        raw["appearance"]["floating_opacity"] = 0.1
        with self.assertRaises(ConfigError):
            Settings.from_mapping(raw)

    def test_version_two_default_melo_settings_migrate_to_sweet_voice(self) -> None:
        raw = {
            "version": 2,
            "tts": {
                "provider": "sherpa_onnx",
                "voice": "zf_xiaoxiao",
                "speaker_id": 0,
                "model_dir": "",
            },
        }
        settings = Settings.from_mapping(raw)
        self.assertEqual(settings.tts.provider, "sherpa_kokoro")
        self.assertEqual(settings.tts.speaker_id, 47)

    def test_custom_melo_directory_is_not_migrated(self) -> None:
        raw = {
            "version": 2,
            "tts": {
                "provider": "sherpa_onnx",
                "voice": "custom",
                "speaker_id": 2,
                "model_dir": "D:/Models/melo",
            },
        }
        settings = Settings.from_mapping(raw)
        self.assertEqual(settings.tts.provider, "sherpa_onnx")
        self.assertEqual(settings.tts.speaker_id, 2)


if __name__ == "__main__":
    unittest.main()
