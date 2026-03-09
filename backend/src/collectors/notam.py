from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, Callable
from urllib.request import urlopen


DEFAULT_TIMEOUT_SECONDS = 10
NOTAM_ALERT_KEYWORDS = (
    "AIRSPACE RESTRICTION",
    "MILITARY",
    "MISSILE",
    "RESTRICTED",
    "TFR",
)
BOOTSTRAP_NOTAM_RESPONSE: dict[str, Any] = {
    "notices": [
        {
            "id": "NOTAM-A1",
            "location": "KADW",
            "classification": "RESTRICTED AIRSPACE",
            "text": "TEMPORARY FLIGHT RESTRICTION FOR MILITARY EXERCISE IN EFFECT.",
            "effective_start": "2026-03-07T08:00:00Z",
            "effective_end": "2026-03-07T14:00:00Z",
        },
        {
            "id": "NOTAM-A2",
            "location": "PAMH",
            "classification": "MISSILE ACTIVITY",
            "text": "MISSILE TEST OPERATIONS. AIRSPACE RESTRICTION ACTIVE.",
            "effective_start": "2026-03-07T09:00:00Z",
            "effective_end": "2026-03-07T12:00:00Z",
        },
        {
            "id": "NOTAM-A3",
            "location": "EGTT",
            "classification": "RUNWAY",
            "text": "RUNWAY LIGHTING MAINTENANCE.",
            "effective_start": "2026-03-07T10:00:00Z",
            "effective_end": "2026-03-07T11:30:00Z",
        },
    ]
}


@dataclass(frozen=True)
class NotamNotice:
    notice_id: str
    location: str | None
    classification: str | None
    text: str
    effective_start: str | None
    effective_end: str | None


@dataclass(frozen=True)
class NotamObservation:
    collected_at: datetime
    status: str
    raw_payload: dict[str, Any]
    notices: list[NotamNotice]
    notam_spike: float


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _notice_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("notices"), list):
        return payload["notices"]
    if isinstance(payload.get("items"), list):
        return payload["items"]
    if isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def parse_notices(payload: dict[str, Any]) -> list[NotamNotice]:
    notices: list[NotamNotice] = []
    for row in _notice_rows(payload):
        notices.append(
            NotamNotice(
                notice_id=str(row.get("id") or row.get("notice_id") or "unknown"),
                location=row.get("location"),
                classification=row.get("classification") or row.get("type"),
                text=str(row.get("text") or row.get("message") or ""),
                effective_start=row.get("effective_start"),
                effective_end=row.get("effective_end"),
            )
        )
    return notices


def compute_notam_spike(notices: list[NotamNotice]) -> float:
    flagged_count = 0
    for notice in notices:
        haystack = f"{notice.classification or ''} {notice.text}".upper()
        if any(keyword in haystack for keyword in NOTAM_ALERT_KEYWORDS):
            flagged_count += 1
    score = (len(notices) * 0.08) + (flagged_count * 0.18)
    return round(min(score, 1.0), 4)


class NotamCollector:
    def __init__(
        self,
        source_url: str | None = None,
        payload_loader: Callable[[], dict[str, Any]] | None = None,
        fallback_payload: dict[str, Any] | None = None,
    ) -> None:
        self._source_url = source_url
        self._payload_loader = payload_loader or self._load_live_payload
        self._fallback_payload = fallback_payload or BOOTSTRAP_NOTAM_RESPONSE

    def fetch_observation(self) -> NotamObservation:
        try:
            payload = self._payload_loader()
            status = "active"
        except Exception:
            payload = self._fallback_payload
            status = "degraded"

        notices = parse_notices(payload)
        return NotamObservation(
            collected_at=_utc_now(),
            status=status,
            raw_payload=payload,
            notices=notices,
            notam_spike=compute_notam_spike(notices),
        )

    def _load_live_payload(self) -> dict[str, Any]:
        if not self._source_url:
            raise RuntimeError("NOTAM source URL is not configured.")
        with urlopen(self._source_url, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
