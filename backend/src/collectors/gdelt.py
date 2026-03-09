from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, Callable
from urllib.request import urlopen


DEFAULT_TIMEOUT_SECONDS = 10
GDELT_ALERT_KEYWORDS = (
    "AIRSTRIKE",
    "CONFLICT",
    "MISSILE",
    "MOBILIZATION",
    "STRIKE",
    "TROOPS",
)
BOOTSTRAP_GDELT_RESPONSE: dict[str, Any] = {
    "articles": [
        {
            "id": "GDELT-1",
            "title": "Missile alert follows sudden regional mobilization",
            "body": "Officials report military mobilization and expanding conflict risk.",
            "source": "Example Wire",
            "published_at": "2026-03-07T08:20:00Z",
        },
        {
            "id": "GDELT-2",
            "title": "Airspace restrictions tighten after strike warnings",
            "body": "Analysts cite possible strike scenarios and increasing military posture.",
            "source": "Open Source Monitor",
            "published_at": "2026-03-07T08:35:00Z",
        },
        {
            "id": "GDELT-3",
            "title": "Troops repositioned near border checkpoints",
            "body": "Local media discuss conflict escalation and security operations.",
            "source": "Regional Desk",
            "published_at": "2026-03-07T08:50:00Z",
        },
        {
            "id": "GDELT-4",
            "title": "Commodity markets react to diplomatic talks",
            "body": "Investors remain cautious as negotiators continue meetings.",
            "source": "Market Desk",
            "published_at": "2026-03-07T09:00:00Z",
        },
    ]
}


@dataclass(frozen=True)
class GdeltArticle:
    article_id: str
    title: str
    body: str
    source: str | None
    published_at: str | None


@dataclass(frozen=True)
class GdeltObservation:
    collected_at: datetime
    status: str
    raw_payload: dict[str, Any]
    articles: list[GdeltArticle]
    news_volume: float


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _article_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("articles"), list):
        return payload["articles"]
    if isinstance(payload.get("items"), list):
        return payload["items"]
    if isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def parse_articles(payload: dict[str, Any]) -> list[GdeltArticle]:
    articles: list[GdeltArticle] = []
    for row in _article_rows(payload):
        articles.append(
            GdeltArticle(
                article_id=str(row.get("id") or row.get("article_id") or "unknown"),
                title=str(row.get("title") or row.get("headline") or ""),
                body=str(row.get("body") or row.get("summary") or row.get("content") or ""),
                source=row.get("source"),
                published_at=row.get("published_at"),
            )
        )
    return articles


def compute_news_volume(articles: list[GdeltArticle]) -> float:
    flagged_count = 0
    for article in articles:
        haystack = f"{article.title} {article.body}".upper()
        if any(keyword in haystack for keyword in GDELT_ALERT_KEYWORDS):
            flagged_count += 1
    score = (len(articles) * 0.07) + (flagged_count * 0.16)
    return round(min(score, 1.0), 4)


class GdeltCollector:
    def __init__(
        self,
        source_url: str | None = None,
        payload_loader: Callable[[], dict[str, Any]] | None = None,
        fallback_payload: dict[str, Any] | None = None,
    ) -> None:
        self._source_url = source_url
        self._payload_loader = payload_loader or self._load_live_payload
        self._fallback_payload = fallback_payload or BOOTSTRAP_GDELT_RESPONSE

    def fetch_observation(self) -> GdeltObservation:
        try:
            payload = self._payload_loader()
            status = "active"
        except Exception:
            payload = self._fallback_payload
            status = "degraded"

        articles = parse_articles(payload)
        return GdeltObservation(
            collected_at=_utc_now(),
            status=status,
            raw_payload=payload,
            articles=articles,
            news_volume=compute_news_volume(articles),
        )

    def _load_live_payload(self) -> dict[str, Any]:
        if not self._source_url:
            raise RuntimeError("GDELT source URL is not configured.")
        with urlopen(self._source_url, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
