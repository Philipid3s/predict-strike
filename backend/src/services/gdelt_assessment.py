from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.collectors.gdelt import (
    GdeltArticle,
    article_source_label,
    extract_article_regions,
)
from src.models.schemas import GdeltSignalAssessment


logger = logging.getLogger(__name__)

PROMPT_VERSION = "gdelt-strike-v1"
DEFAULT_AI_API_URL = "https://api.openai.com/v1/chat/completions"
RECENT_ARTICLE_WINDOW_HOURS = 24 * 14

PROMPT_TEMPLATE = """Role: You are a geopolitical risk analyst focused on imminent US/NATO strike indicators.

Task: Assess whether the supplied recent news article set indicates an imminent strike or attack by the United States or NATO against any country.

Rules:
1. Use only the provided article set.
2. Focus on US/NATO action-indicative reporting, not generic conflict coverage.
3. Prefer hard indicators such as strike warnings, force posture shifts, airbase activity, deployment language, missile/airstrike preparation, evacuation warnings, or named US/NATO military actors.
4. If evidence is weak, return a low percentage.
5. Choose the most likely target region and country only if supported by the article set.

Return only valid JSON with this exact shape:
{{
  "probability_percent": 0,
  "target_region": "region or null",
  "target_country": "country or null",
  "summary": "short explanation"
}}

Article set:
{articles_json}
"""


@dataclass(frozen=True)
class GdeltAssessmentConfig:
    api_url: str | None
    api_key: str | None
    model: str | None
    timeout_seconds: int = 15


def _truncate_debug_text(value: Any, *, limit: int = 500) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def compute_article_freshness_score(
    article: GdeltArticle, now: datetime | None = None
) -> float:
    published_at = _parse_published_at(article.published_at)
    if published_at is None:
        return 0.15

    reference_now = now or datetime.now(UTC)
    age_hours = max((reference_now - published_at).total_seconds() / 3600.0, 0.0)
    if age_hours <= 6:
        return 1.0
    if age_hours <= 12:
        return 0.85
    if age_hours <= 24:
        return 0.65
    if age_hours <= 48:
        return 0.4
    if age_hours <= 72:
        return 0.2
    return 0.05


def is_recent_article(article: GdeltArticle, now: datetime | None = None) -> bool:
    published_at = _parse_published_at(article.published_at)
    if published_at is None:
        return False

    reference_now = now or datetime.now(UTC)
    age_hours = max((reference_now - published_at).total_seconds() / 3600.0, 0.0)
    return age_hours <= RECENT_ARTICLE_WINDOW_HOURS


def filter_recent_articles(
    articles: Sequence[GdeltArticle], now: datetime | None = None
) -> list[GdeltArticle]:
    reference_now = now or datetime.now(UTC)
    return [article for article in articles if is_recent_article(article, reference_now)]


def _article_haystack(article: GdeltArticle) -> str:
    return f"{article.title} {article.body}".upper()


def is_us_nato_actor_article(article: GdeltArticle) -> bool:
    haystack = _article_haystack(article)
    actor_terms = (
        "NATO",
        "UNITED STATES",
        "US MILITARY",
        "U.S. MILITARY",
        "PENTAGON",
        "USAF",
        "U.S. AIR FORCE",
        "US NAVY",
        "U.S. NAVY",
        "ALLIED FORCES",
    )
    return any(term in haystack for term in actor_terms)


def is_action_indicative_article(article: GdeltArticle) -> bool:
    haystack = _article_haystack(article)
    action_terms = (
        "AIRSTRIKE",
        "ATTACK",
        "BOMBING",
        "DEPLOYMENT",
        "ESCALATION",
        "EVACUATION WARNING",
        "FORCE POSTURE",
        "MISSILE",
        "SORTIE",
        "STRIKE",
        "TARGET",
        "WARNING",
    )
    return any(term in haystack for term in action_terms)


def is_us_nato_action_article(article: GdeltArticle) -> bool:
    return is_us_nato_actor_article(article) and is_action_indicative_article(article)


def build_signal_article_set(
    articles: Sequence[GdeltArticle],
    *,
    now: datetime | None = None,
    limit: int = 12,
) -> list[GdeltArticle]:
    reference_now = now or datetime.now(UTC)
    recent_articles = filter_recent_articles(articles, reference_now)
    ranked = sorted(
        recent_articles,
        key=lambda article: (
            is_us_nato_action_article(article),
            compute_article_freshness_score(article, reference_now),
            article.published_at or "",
        ),
        reverse=True,
    )

    selected: list[GdeltArticle] = [
        article for article in ranked if is_us_nato_action_article(article)
    ][:limit]
    if selected:
        return selected
    return ranked[: min(limit, len(ranked))]


def build_assessment_prompt(
    articles: Sequence[GdeltArticle],
    *,
    now: datetime | None = None,
) -> str:
    reference_now = now or datetime.now(UTC)
    condensed_articles = [
        {
            "title": article.title,
            "source": article_source_label(article),
            "published_at": article.published_at,
            "freshness_score": compute_article_freshness_score(article, reference_now),
            "regions": extract_article_regions(article),
            "is_us_nato_actor_article": is_us_nato_actor_article(article),
            "is_action_indicative_article": is_action_indicative_article(article),
            "body_excerpt": article.body[:280],
            "url": article.url,
        }
        for article in articles
    ]
    return PROMPT_TEMPLATE.format(
        articles_json=json.dumps(condensed_articles, indent=2)
    )


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("AI response did not include choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("AI response did not include a message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_chunks = [
            item.get("text")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if text_chunks:
            return "".join(text_chunks)
    raise ValueError("AI response did not include text content")


def _parse_assessment_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("AI response did not contain valid JSON") from None
        return json.loads(content[start : end + 1])


class GdeltStrikeAssessmentService:
    def __init__(
        self,
        config: GdeltAssessmentConfig,
        request_sender: Callable[[Request, int], dict[str, Any]] | None = None,
    ) -> None:
        self._config = config
        self._request_sender = request_sender or self._send_request

    def assess_articles(
        self, articles: Sequence[GdeltArticle]
    ) -> GdeltSignalAssessment:
        signal_articles = build_signal_article_set(articles)
        if not signal_articles:
            return GdeltSignalAssessment(
                status="ready",
                prompt_version=PROMPT_VERSION,
                probability_percent=0,
                target_region=None,
                target_country=None,
                summary="No recent GDELT articles were available for assessment.",
                assessed_article_count=0,
                freshness_score=0.0,
            )

        freshness_score = round(
            sum(compute_article_freshness_score(article) for article in signal_articles)
            / len(signal_articles),
            4,
        )

        if not self._config.api_key or not self._config.model:
            return GdeltSignalAssessment(
                status="disabled",
                prompt_version=PROMPT_VERSION,
                probability_percent=None,
                target_region=None,
                target_country=None,
                summary=(
                    "AI assessment is disabled because GDELT_AI_API_KEY or "
                    "GDELT_AI_MODEL is not configured."
                ),
                assessed_article_count=len(signal_articles),
                freshness_score=freshness_score,
            )

        request = Request(
            self._config.api_url or DEFAULT_AI_API_URL,
            data=json.dumps(
                {
                    "model": self._config.model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You analyze recent GDELT article clusters for imminent "
                                "US/NATO strike indicators."
                            ),
                        },
                        {
                            "role": "user",
                            "content": build_assessment_prompt(signal_articles),
                        },
                    ],
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            payload = self._request_sender(request, self._config.timeout_seconds)
        except HTTPError as exc:
            status_code = getattr(exc, "code", "unknown")
            response_body = ""
            try:
                response_body = exc.read().decode("utf-8", errors="replace")
            except OSError:
                response_body = ""
            logger.warning(
                "GDELT AI upstream returned HTTP %s: %s",
                status_code,
                _truncate_debug_text(response_body or exc.reason),
            )
            return self._build_error_assessment(
                "AI request failed with an upstream HTTP error.",
                len(signal_articles),
                freshness_score,
            )
        except TimeoutError:
            logger.warning(
                "GDELT AI request timed out after %s seconds",
                self._config.timeout_seconds,
            )
            return self._build_error_assessment(
                "AI request timed out while waiting for the upstream model provider.",
                len(signal_articles),
                freshness_score,
            )
        except URLError as exc:
            logger.warning(
                "GDELT AI request could not reach upstream provider: %s",
                _truncate_debug_text(exc.reason),
            )
            return self._build_error_assessment(
                "AI request failed to reach the upstream model provider.",
                len(signal_articles),
                freshness_score,
            )
        except OSError as exc:
            logger.warning(
                "GDELT AI request failed with OS error: %s",
                _truncate_debug_text(exc),
            )
            return self._build_error_assessment(
                "AI request could not be completed because of a local network or transport error.",
                len(signal_articles),
                freshness_score,
            )

        try:
            response_content = _extract_message_content(payload)
            parsed = _parse_assessment_json(response_content)
        except ValueError as exc:
            logger.warning(
                "GDELT AI response could not be parsed as required JSON: %s; payload=%s",
                exc,
                _truncate_debug_text(json.dumps(payload, ensure_ascii=True)),
            )
            return self._build_error_assessment(
                "AI response could not be parsed as the required JSON object.",
                len(signal_articles),
                freshness_score,
            )

        probability = parsed.get("probability_percent")
        target_region = parsed.get("target_region")
        target_country = parsed.get("target_country")
        summary = parsed.get("summary")
        if not isinstance(probability, int) or not 0 <= probability <= 100:
            valid = False
        else:
            valid = (
                (target_region is None or isinstance(target_region, str))
                and (target_country is None or isinstance(target_country, str))
                and isinstance(summary, str)
                and bool(summary.strip())
            )
        if not valid:
            logger.warning(
                "GDELT AI response JSON did not match required fields: %s",
                _truncate_debug_text(json.dumps(parsed, ensure_ascii=True)),
            )
            return self._build_error_assessment(
                "AI response JSON did not match the required fields.",
                len(signal_articles),
                freshness_score,
            )

        return GdeltSignalAssessment(
            status="ready",
            prompt_version=PROMPT_VERSION,
            probability_percent=probability,
            target_region=target_region.strip() if isinstance(target_region, str) and target_region.strip() else None,
            target_country=target_country.strip() if isinstance(target_country, str) and target_country.strip() else None,
            summary=summary.strip(),
            assessed_article_count=len(signal_articles),
            freshness_score=freshness_score,
        )

    @staticmethod
    def _build_error_assessment(
        summary: str,
        assessed_article_count: int,
        freshness_score: float,
    ) -> GdeltSignalAssessment:
        return GdeltSignalAssessment(
            status="error",
            prompt_version=PROMPT_VERSION,
            probability_percent=None,
            target_region=None,
            target_country=None,
            summary=summary,
            assessed_article_count=assessed_article_count,
            freshness_score=freshness_score,
        )

    @staticmethod
    def _send_request(request: Request, timeout_seconds: int) -> dict[str, Any]:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def probability_to_signal_feature(assessment: GdeltSignalAssessment) -> float:
    if assessment.status != "ready" or assessment.probability_percent is None:
        return 0.0
    return round(assessment.probability_percent / 100.0, 4)


def derive_region_focus_from_assessment(
    assessment: GdeltSignalAssessment, fallback: str
) -> str:
    if assessment.status != "ready":
        return fallback
    if assessment.target_country:
        return assessment.target_country
    if assessment.target_region:
        return assessment.target_region
    return fallback
