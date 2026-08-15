from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_SCRIPT = PROJECT_ROOT / "jarvis" / "static" / "app.js"
INDEX_HTML = PROJECT_ROOT / "jarvis" / "static" / "index.html"


class FrontendContractTests(unittest.TestCase):
    def test_every_ui_lookup_is_registered(self) -> None:
        source = APP_SCRIPT.read_text(encoding="utf-8")
        registry_match = re.search(
            r"const ui = Object\.fromEntries\(\[(.*?)\]\.map",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(registry_match)
        registered = set(re.findall(r'"([a-z0-9-]+)"', registry_match.group(1)))
        referenced = set(re.findall(r'ui\["([a-z0-9-]+)"\]', source))

        self.assertEqual(referenced - registered, set())

        html = INDEX_HTML.read_text(encoding="utf-8")
        html_ids = set(re.findall(r'id="([a-z0-9-]+)"', html))
        self.assertEqual(registered - html_ids, set())


if __name__ == "__main__":
    unittest.main()
