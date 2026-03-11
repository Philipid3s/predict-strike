from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, Callable
from urllib.parse import urlparse
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
# Official GDELT DOC 2.0 article-list responses are expected to expose an
# `articles` array with article metadata such as `url`, `title`, `seendate`,
# and `domain`.
BOOTSTRAP_GDELT_RESPONSE: dict[str, Any] = {
    "articles": [
        {
            "id": "GDELT-1",
            "title": "Missile alert follows sudden Black Sea mobilization",
            "body": "Officials report military mobilization and expanding conflict risk across the Black Sea corridor.",
            "source": "Example Wire",
            "published_at": "2026-03-07T08:20:00Z",
            "url": "https://examplewire.test/black-sea-mobilization",
        },
        {
            "id": "GDELT-2",
            "title": "Eastern Mediterranean airspace restrictions tighten after strike warnings",
            "body": "Analysts cite possible strike scenarios and increasing military posture across the Eastern Mediterranean.",
            "source": "Open Source Monitor",
            "published_at": "2026-03-07T08:35:00Z",
            "url": "https://osm.test/eastern-med-airspace",
        },
        {
            "id": "GDELT-3",
            "title": "Troops repositioned near Persian Gulf logistics hubs",
            "body": "Local media discuss conflict escalation, logistics, and security operations around the Persian Gulf.",
            "source": "Regional Desk",
            "published_at": "2026-03-07T08:50:00Z",
            "url": "https://regionaldesk.test/persian-gulf-logistics",
        },
        {
            "id": "GDELT-4",
            "title": "Commodity markets react to diplomatic talks",
            "body": "Investors remain cautious as negotiators continue meetings.",
            "source": "Market Desk",
            "published_at": "2026-03-07T09:00:00Z",
            "url": "https://marketdesk.test/diplomatic-talks",
        },
    ]
}
GDELT_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Conflict & strikes": ("AIRSTRIKE", "CONFLICT", "MISSILE", "STRIKE"),
    "Mobilization & troop movement": ("MOBILIZATION", "TROOPS", "REPOSITIONED", "POSTURE"),
    "Airspace & aviation disruption": ("AIRSPACE", "RESTRICTIONS", "FLIGHT", "AVIATION"),
    "Diplomacy & markets": ("DIPLOMATIC", "NEGOTIATORS", "MARKETS", "INVESTORS"),
}
GDELT_REGION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Black Sea": ("BLACK SEA",),
    "Eastern Mediterranean": ("EASTERN MEDITERRANEAN",),
    "Persian Gulf": ("PERSIAN GULF",),
}


@dataclass(frozen=True)
class GdeltArticle:
    article_id: str
    title: str
    body: str
    source: str | None
    published_at: str | None
    url: str | None


@dataclass(frozen=True)
class GdeltObservation:
    collected_at: datetime
    status: str
    raw_payload: dict[str, Any]
    articles: list[GdeltArticle]
    news_volume: float
    fallback_reason: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def is_gdelt_doc_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("articles"), list)


def _doc_article_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not is_gdelt_doc_payload(payload):
        raise ValueError("Payload does not match GDELT DOC 2.0 article-list JSON.")
    return payload["articles"]


def _normalize_published_at(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    candidates = (
        text,
        text.replace("Z", "+00:00"),
    )
    formats = (
        "%Y%m%dT%H%M%SZ",
        "%Y%m%d%H%M%S",
        "%Y-%m-%d %H:%M:%S",
    )

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass

    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue

    return None


def parse_articles(payload: dict[str, Any]) -> list[GdeltArticle]:
    articles: list[GdeltArticle] = []
    for row in _doc_article_rows(payload):
        if not isinstance(row, dict):
            continue
        article_url = row.get("url") or row.get("url_mobile") or row.get("link")
        article_source = row.get("source") or row.get("domain") or row.get("sourcecountry")
        articles.append(
            GdeltArticle(
                article_id=str(
                    row.get("id")
                    or row.get("url")
                    or row.get("url_mobile")
                    or row.get("article_id")
                    or "unknown"
                ),
                title=str(row.get("title") or row.get("headline") or ""),
                body=str(row.get("body") or row.get("summary") or row.get("content") or ""),
                source=str(article_source) if article_source is not None else None,
                published_at=_normalize_published_at(
                    row.get("published_at") or row.get("seendate")
                ),
                url=str(article_url) if article_url is not None else None,
            )
        )
    return articles


def article_haystack(article: GdeltArticle) -> str:
    return f"{article.title} {article.body}".upper()


def is_alert_article(article: GdeltArticle) -> bool:
    haystack = article_haystack(article)
    return any(keyword in haystack for keyword in GDELT_ALERT_KEYWORDS)


def extract_article_themes(article: GdeltArticle) -> list[str]:
    haystack = article_haystack(article)
    return [
        theme
        for theme, keywords in GDELT_THEME_KEYWORDS.items()
        if any(keyword in haystack for keyword in keywords)
    ]


def extract_article_regions(article: GdeltArticle) -> list[str]:
    haystack = article_haystack(article)
    return [
        region
        for region, keywords in GDELT_REGION_KEYWORDS.items()
        if any(keyword in haystack for keyword in keywords)
    ]


def article_source_label(article: GdeltArticle) -> str:
    if article.url:
        hostname = urlparse(article.url).hostname
        if hostname:
            return hostname
    return article.source or "unknown"


def compute_news_volume(articles: list[GdeltArticle]) -> float:
    flagged_count = sum(1 for article in articles if is_alert_article(article))
    score = (len(articles) * 0.07) + (flagged_count * 0.16)
    return round(min(score, 1.0), 4)


class GdeltCollector:
    def __init__(
        self,
        source_url: str | None = None,
        payload_loader: Callable[[], dict[str, Any]] | None = None,
        fallback_payload: dict[str, Any] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._source_url = source_url
        self._timeout_seconds = max(timeout_seconds, 1)
        self._payload_loader = payload_loader or self._load_live_payload
        self._fallback_payload = fallback_payload or BOOTSTRAP_GDELT_RESPONSE

    def fetch_observation(self) -> GdeltObservation:
        fallback_reason: str | None = None
        try:
            payload = self._payload_loader()
            if not is_gdelt_doc_payload(payload):
                raise ValueError("GDELT DOC 2.0 payload must include an `articles` array.")
            articles = parse_articles(payload)
            if payload["articles"] and not articles:
                raise ValueError("GDELT DOC 2.0 payload did not contain any usable article rows.")
            status = "active"
        except Exception as exc:
            payload = self._fallback_payload
            articles = parse_articles(payload)
            status = "degraded"
            fallback_reason = f"{exc.__class__.__name__}: {exc}"

        return GdeltObservation(
            collected_at=_utc_now(),
            status=status,
            raw_payload=payload,
            articles=articles,
            news_volume=compute_news_volume(articles),
            fallback_reason=fallback_reason,
        )

    def _load_live_payload(self) -> dict[str, Any]:
        if not self._source_url:
            raise RuntimeError("GDELT DOC 2.0 source URL is not configured.")
        with urlopen(self._source_url, timeout=self._timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
