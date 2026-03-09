from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from src.collectors.pizzint import DEFAULT_PIZZINT_DASHBOARD_URL, fetch_dashboard_payload


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._buffer = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self) -> bytes:
        return self._buffer.read()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class PizzintCollectorTests(unittest.TestCase):
    def test_fetch_dashboard_payload_uses_browser_like_headers(self) -> None:
        captured = {}

        def _fake_urlopen(request, timeout: int = 0):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["timeout"] = timeout
            return _FakeResponse({"success": True, "data": []})

        with patch("src.collectors.pizzint.urlopen", side_effect=_fake_urlopen):
            payload = fetch_dashboard_payload()

        self.assertEqual(payload["success"], True)
        self.assertEqual(captured["url"], DEFAULT_PIZZINT_DASHBOARD_URL)
        self.assertEqual(captured["timeout"], 8)
        self.assertIn("User-agent", captured["headers"])
        self.assertIn("Accept", captured["headers"])
        self.assertIn("Referer", captured["headers"])


if __name__ == "__main__":
    unittest.main()
