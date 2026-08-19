from __future__ import annotations

import unittest

from jarvis.speech import _multipart_audio_body
from workers.sensevoice_server import parse_multipart


class WorkerProtocolTests(unittest.TestCase):
    def test_main_app_and_sensevoice_worker_share_multipart_protocol(self) -> None:
        body, content_type = _multipart_audio_body(
            {
                "model": "SenseVoiceSmall",
                "language": "zh",
                "response_format": "json",
            },
            b"recorded-audio",
            "audio/webm",
        )

        audio, filename, fields = parse_multipart(content_type, body)

        self.assertEqual(audio, b"recorded-audio")
        self.assertEqual(filename, "recording.webm")
        self.assertEqual(fields["model"], "SenseVoiceSmall")
        self.assertEqual(fields["language"], "zh")


if __name__ == "__main__":
    unittest.main()
