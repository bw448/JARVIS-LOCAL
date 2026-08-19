from __future__ import annotations

import unittest

from jarvis.app import STATIC_DIR


class FrontendContractTests(unittest.TestCase):
    def test_identity_does_not_replace_hud_visuals(self) -> None:
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        floating = (STATIC_DIR / "floating.html").read_text(encoding="utf-8")
        app = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        floating_script = (STATIC_DIR / "floating.js").read_text(encoding="utf-8")

        self.assertIn('id="core-monogram"><img src="/static/mark.svg"', index)
        self.assertIn('id="float-monogram" class="hud-name"><img', floating)
        self.assertNotIn('ui["core-monogram"].textContent', app)
        self.assertNotIn("monogram.textContent", floating_script)

    def test_realtime_chat_and_local_quality_tts_are_exposed(self) -> None:
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        app = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("/api/chat/stream", app)
        self.assertIn("readChatStream", app)
        self.assertIn("本地高品质服务 / 兼容 TTS", index)
        self.assertIn("Qwen3-TTS、CosyVoice", index)

    def test_computer_control_requires_visible_confirmation(self) -> None:
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        app = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="setting-computer-control"', index)
        self.assertIn("window.confirm", app)
        self.assertIn("/api/tools/resolve", app)


if __name__ == "__main__":
    unittest.main()
