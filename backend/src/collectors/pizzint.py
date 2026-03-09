from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_PIZZINT_DASHBOARD_URL = "https://www.pizzint.watch/api/dashboard-data"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.pizzint.watch/",
}


def fetch_dashboard_payload(
    *,
    source_url: str | None = None,
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    url = (source_url or DEFAULT_PIZZINT_DASHBOARD_URL).strip() or DEFAULT_PIZZINT_DASHBOARD_URL
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise RuntimeError("pizzint dashboard returned an unexpected payload")
    return payload
