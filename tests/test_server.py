from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib import error, request

from jarvis.app import JarvisApplication, create_server
from jarvis.config import SettingsStore


class MemorySecretStore:
    def __init__(self) -> None:
        self.value = ""

    def get_brain_api_key(self) -> str:
        return self.value

    def has_brain_api_key(self) -> bool:
        return bool(self.value)

    def set_brain_api_key(self, value: str | None) -> None:
        self.value = (value or "").strip()


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.application = JarvisApplication(
            SettingsStore(Path(self.temporary.name)), MemorySecretStore()
        )
        self.server = create_server("127.0.0.1", 0, self.application)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def test_bootstrap_has_no_secret_value(self) -> None:
        with request.urlopen(f"{self.base_url}/api/bootstrap", timeout=2) as response:
            payload = json.load(response)
        self.assertEqual(payload["settings"]["identity"]["assistant_name"], "JARVIS")
        self.assertEqual(payload["app"]["name"], "JARVIS LOCAL")
        self.assertEqual(payload["app"]["version"], "0.7.0")
        self.assertEqual(payload["settings"]["appearance"]["theme"], "cyan")
        self.assertEqual(payload["settings"]["appearance"]["floating_opacity"], 0.85)
        self.assertTrue(payload["settings"]["interaction"]["proactive_speech"])
        self.assertNotIn("api_key", payload["settings"].get("brain", {}))
        self.assertIs(payload["secrets"]["brain_api_key_saved"], False)

    def test_root_serves_local_ui_with_security_policy(self) -> None:
        with request.urlopen(f"{self.base_url}/", timeout=2) as response:
            html = response.read().decode("utf-8")
            policy = response.headers["Content-Security-Policy"]
        self.assertIn("PRIVATE SIGNAL DESK", html)
        self.assertIn("signal-core", html)
        self.assertIn("jarvis-hud-logo.png", html)
        self.assertIn("default-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)

        with request.urlopen(f"{self.base_url}/floating", timeout=2) as response:
            floating = response.read().decode("utf-8")
        self.assertIn("JARVIS 悬浮助手", floating)
        self.assertIn("贾维斯圆形 HUD", floating)
        self.assertIn("float-action", floating)

        with request.urlopen(
            f"{self.base_url}/static/jarvis-hud-logo.png", timeout=2
        ) as response:
            logo = response.read()
            logo_type = response.headers["Content-Type"]
        self.assertEqual(logo[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(logo_type, "image/png")

    def test_settings_can_change_names(self) -> None:
        with request.urlopen(f"{self.base_url}/api/bootstrap", timeout=2) as response:
            state = json.load(response)
        state["settings"]["identity"]["assistant_name"] = "星期五"
        state["settings"]["identity"]["owner_name"] = "老板"
        outgoing = request.Request(
            f"{self.base_url}/api/settings",
            data=json.dumps({"settings": state["settings"]}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": self.base_url},
            method="POST",
        )
        with request.urlopen(outgoing, timeout=2) as response:
            updated = json.load(response)
        self.assertEqual(updated["settings"]["identity"]["assistant_name"], "星期五")
        self.assertEqual(updated["settings"]["identity"]["owner_name"], "老板")

    def test_voice_status_does_not_expose_secrets(self) -> None:
        with request.urlopen(f"{self.base_url}/api/voice/status", timeout=2) as response:
            payload = json.load(response)
        self.assertIn("tts", payload["capabilities"])
        self.assertEqual(payload["settings"]["tts"]["provider"], "sherpa_kokoro")
        self.assertEqual(payload["settings"]["tts"]["speaker_id"], 47)
        self.assertEqual(
            payload["capabilities"]["tts"]["voice_presets"][0]["voice"],
            "zf_xiaoxiao",
        )
        self.assertNotIn("brain", payload["settings"])
        self.assertNotIn("api_key", json.dumps(payload))

    def test_voice_test_can_request_browser_fallback(self) -> None:
        with request.urlopen(f"{self.base_url}/api/bootstrap", timeout=2) as response:
            state = json.load(response)
        state["settings"]["tts"]["provider"] = "system"
        outgoing = request.Request(
            f"{self.base_url}/api/voice/test",
            data=json.dumps({"settings": state["settings"]}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": self.base_url},
            method="POST",
        )
        with request.urlopen(outgoing, timeout=2) as response:
            payload = json.load(response)
        self.assertEqual(payload["mode"], "browser")
        self.assertIn("JARVIS", payload["text"])

    def test_voice_test_accepts_unsaved_voice_preview(self) -> None:
        captured = {}

        def fake_synthesize(settings, text):
            captured["voice"] = settings.tts.voice
            captured["speaker_id"] = settings.tts.speaker_id
            return None

        self.application.speech.synthesize = fake_synthesize
        with request.urlopen(f"{self.base_url}/api/bootstrap", timeout=2) as response:
            state = json.load(response)
        state["settings"]["tts"]["voice"] = "zf_xiaoni"
        state["settings"]["tts"]["speaker_id"] = 46
        outgoing = request.Request(
            f"{self.base_url}/api/voice/test",
            data=json.dumps({"settings": state["settings"]}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": self.base_url},
            method="POST",
        )
        with request.urlopen(outgoing, timeout=2) as response:
            payload = json.load(response)
        self.assertEqual(payload["mode"], "browser")
        self.assertEqual(captured, {"voice": "zf_xiaoni", "speaker_id": 46})

    def test_chat_stream_endpoint_uses_ndjson(self) -> None:
        class FakeBrain:
            def stream(self, settings, messages, api_key="", voice_context=""):
                yield "马上"
                yield "为你处理。"

        self.application.brain = FakeBrain()
        outgoing = request.Request(
            f"{self.base_url}/api/chat/stream",
            data=json.dumps(
                {"messages": [{"role": "user", "content": "开始"}]}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": self.base_url},
            method="POST",
        )
        with request.urlopen(outgoing, timeout=2) as response:
            lines = [json.loads(line) for line in response if line.strip()]
            content_type = response.headers.get_content_type()

        self.assertEqual(content_type, "application/x-ndjson")
        self.assertEqual([line["type"] for line in lines], ["delta", "delta", "done"])
        self.assertEqual(lines[-1]["answer"], "马上为你处理。")

    def test_tool_resolution_requires_enabled_control_and_one_time_proposal(self) -> None:
        disabled = request.Request(
            f"{self.base_url}/api/tools/resolve",
            data=json.dumps({"proposal_id": "missing", "approved": False}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json", "Origin": self.base_url},
            method="POST",
        )
        with self.assertRaises(error.HTTPError) as captured:
            request.urlopen(disabled, timeout=2)
        self.assertEqual(captured.exception.code, 400)
        captured.exception.close()

        self.application._settings.interaction.computer_control_enabled = True
        proposal = self.application.computer.propose(
            "open_application", {"application": "calculator"}
        )
        outgoing = request.Request(
            f"{self.base_url}/api/tools/resolve",
            data=json.dumps(
                {"proposal_id": proposal["proposal_id"], "approved": False}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": self.base_url},
            method="POST",
        )
        with request.urlopen(outgoing, timeout=2) as response:
            payload = json.load(response)

        self.assertFalse(payload["executed"])
        self.assertIn("已取消", payload["message"])


if __name__ == "__main__":
    unittest.main()
