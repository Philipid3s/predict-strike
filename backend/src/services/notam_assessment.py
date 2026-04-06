from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.collectors.notam import NOTAM_ALERT_KEYWORDS, NotamNotice
from src.models.schemas import NotamSignalAssessment


logger = logging.getLogger(__name__)

PROMPT_VERSION = "notam-strike-v2"
DEFAULT_AI_API_URL = "https://api.openai.com/v1/chat/completions"
MAX_CONDENSED_NOTICES = 12

NOTAM_SIGNAL_KEYWORDS = (
    "AIRSPACE RESTRICTION",
    "RESTRICTED AIRSPACE",
    "MILITARY",
    "MISSILE",
    "EXERCISE",
    "LIVE FIRE",
    "TFR",
    "DRONE",
    "UAS",
    "WEAPON",
    "FIRING",
    "SECURITY",
    "CLOSURE",
    "AIR DEFENSE",
    "TEST",
    "WARNING",
)

NOTAM_URGENT_KEYWORDS = (
    "IMMEDIATE",
    "URGENT",
    "UNTIL FURTHER NOTICE",
    "NOW",
    "ACTIVE",
)

NOTAM_LOCATION_HINTS: tuple[tuple[str, str, str], ...] = (
    ("EG", "United Kingdom", "Europe"),
    ("ED", "Germany", "Europe"),
    ("EK", "Denmark", "Europe"),
    ("EN", "Norway", "Europe"),
    ("ES", "Sweden", "Europe"),
    ("ET", "Germany", "Europe"),
    ("LF", "France", "Europe"),
    ("LE", "Spain", "Europe"),
    ("LI", "Italy", "Europe"),
    ("LK", "Czech Republic", "Europe"),
    ("LH", "Hungary", "Europe"),
    ("LR", "Romania", "Europe"),
    ("LZ", "Slovakia", "Europe"),
    ("LL", "Israel", "Middle East"),
    ("OJ", "Jordan", "Middle East"),
    ("OK", "Kuwait", "Middle East"),
    ("OT", "Qatar", "Middle East"),
    ("OE", "Saudi Arabia", "Middle East"),
    ("OM", "United Arab Emirates", "Middle East"),
    ("OR", "Iraq", "Middle East"),
    ("OI", "Iran", "Middle East"),
    ("K", "United States", "North America"),
    ("P", "United States", "North America"),
    ("C", "Canada", "North America"),
    ("RJ", "Japan", "Asia"),
    ("RK", "South Korea", "Asia"),
    ("YM", "Australia", "Oceania"),
)

NOTAM_TEXT_REGION_HINTS: tuple[tuple[str, str], ...] = (
    ("BLACK SEA", "Black Sea"),
    ("EASTERN MEDITERRANEAN", "Eastern Mediterranean"),
    ("MEDITERRANEAN", "Mediterranean"),
    ("PERSIAN GULF", "Persian Gulf"),
    ("RED SEA", "Red Sea"),
    ("BALTIC", "Baltic region"),
    ("KOREAN PENINSULA", "Korean Peninsula"),
    ("TAIWAN STRAIT", "Taiwan Strait"),
    ("SOUTH CHINA SEA", "South China Sea"),
    ("HORN OF AFRICA", "Horn of Africa"),
    ("SAHEL", "Sahel"),
    ("UKRAINE", "Ukraine / Western Russia"),
    ("WESTERN RUSSIA", "Ukraine / Western Russia"),
)

COUNTRY_REGION_HINTS: dict[str, str] = {
    "United States": "North America",
    "Canada": "North America",
    "United Kingdom": "Europe",
    "Germany": "Europe",
    "Denmark": "Europe",
    "Norway": "Europe",
    "Sweden": "Europe",
    "France": "Europe",
    "Spain": "Europe",
    "Italy": "Europe",
    "Czech Republic": "Europe",
    "Hungary": "Europe",
    "Romania": "Europe",
    "Slovakia": "Europe",
    "Israel": "Middle East",
    "Jordan": "Middle East",
    "Kuwait": "Middle East",
    "Qatar": "Middle East",
    "Saudi Arabia": "Middle East",
    "United Arab Emirates": "Middle East",
    "Iraq": "Middle East",
    "Iran": "Middle East",
    "Japan": "Asia",
    "South Korea": "Asia",
    "Australia": "Oceania",
}

PROMPT_TEMPLATE = """Role: You are a military aviation and airspace analyst.

Task: Assess the supplied NOTAM cluster for the probability of strike preparation, escalation, or related military activity in a specific country or region.

Rules:
1. Use only the provided NOTAM notices and metadata.
2. Focus on military exercise, missile, restricted airspace, temporary flight restriction, live fire, closure, and security indicators.
3. Return a probability_percent from 0 to 100 that reflects how likely these NOTAMs indicate strike risk in some part of the world.
4. Choose target_region and target_country only when supported by the data.
5. If evidence is weak, return a low percentage and say so plainly.

Return only valid JSON with this exact shape:
{{
  "probability_percent": 0,
  "target_region": "region or null",
  "target_country": "country or null",
  "summary": "short explanation"
}}

Supporting context:
{context_json}
"""


@dataclass(frozen=True)
class NotamAssessmentConfig:
    api_url: str | None
    api_key: str | None
    model: str | None
    timeout_seconds: int = 15


def _truncate_debug_text(value: Any, *, limit: int = 500) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    candidates = [normalized]
    if normalized.endswith("Z"):
        candidates.insert(0, normalized[:-1] + "+00:00")

    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue

    for pattern in ("%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(normalized, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue

    return None


def _notam_haystack(notice: NotamNotice) -> str:
    return f"{notice.classification or ''} {notice.location or ''} {notice.text}".upper()


def _notam_is_alert(notice: NotamNotice) -> bool:
    haystack = f"{notice.classification or ''} {notice.text}".upper()
    return any(keyword in haystack for keyword in NOTAM_ALERT_KEYWORDS)


def _notam_is_restricted(notice: NotamNotice) -> bool:
    haystack = f"{notice.classification or ''} {notice.text}".upper()
    return any(keyword in haystack for keyword in ("RESTRICT", "TFR", "AIRSPACE RESTRICTION"))


def _notam_effective_window_hours(notice: NotamNotice) -> float | None:
    start = _coerce_datetime(notice.effective_start)
    end = _coerce_datetime(notice.effective_end)
    if start is None or end is None:
        return None
    return max((end - start).total_seconds() / 3600.0, 0.0)


def _normalize_location(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(character for character in value.upper() if character.isalnum())
    return normalized or None


def _infer_location_hint(location: str | None) -> tuple[str | None, str | None]:
    normalized_location = _normalize_location(location)
    if normalized_location is None:
        return None, None

    for prefix, country, region in NOTAM_LOCATION_HINTS:
        if normalized_location.startswith(prefix):
            return country, region
    return None, None


def _explicit_region_hint(notice: NotamNotice) -> str | None:
    haystack = _notam_haystack(notice)
    for keyword, region in NOTAM_TEXT_REGION_HINTS:
        if keyword in haystack:
            return region
    return None


def _notice_priority(notice: NotamNotice, location_counts: dict[str, int]) -> tuple[int, int, datetime]:
    start = _coerce_datetime(notice.effective_start)
    end = _coerce_datetime(notice.effective_end)
    effective_dt = end or start or datetime.min.replace(tzinfo=UTC)
    return (
        1 if _notam_is_alert(notice) else 0,
        1 if _notam_is_restricted(notice) else 0,
        effective_dt,
    )


def build_condensed_notam_notices(
    notices: Sequence[NotamNotice], *, limit: int = MAX_CONDENSED_NOTICES
) -> list[NotamNotice]:
    location_counts = Counter(
        notice.location.upper()
        for notice in notices
        if isinstance(notice.location, str) and notice.location.strip()
    )
    return sorted(
        notices,
        key=lambda notice: _notice_priority(notice, dict(location_counts)),
        reverse=True,
    )[:limit]


def _build_context(
    notices: Sequence[NotamNotice],
    condensed_notices: Sequence[NotamNotice],
) -> dict[str, Any]:
    location_counts = Counter(
        notice.location.upper()
        for notice in notices
        if isinstance(notice.location, str) and notice.location.strip()
    )
    classification_counts = Counter(
        notice.classification.strip() if isinstance(notice.classification, str) and notice.classification.strip() else "Unspecified"
        for notice in notices
    )
    country_counts: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    for notice in notices:
        country, region = _infer_location_hint(notice.location)
        if country is not None:
            country_counts[country] += 1
            if region is None:
                region = COUNTRY_REGION_HINTS.get(country)
        explicit_region = _explicit_region_hint(notice)
        if explicit_region is not None:
            region_counts[explicit_region] += 1
        elif region is not None:
            region_counts[region] += 1

    start_values = []
    end_values = []
    for notice in notices:
        start_dt = _coerce_datetime(notice.effective_start)
        end_dt = _coerce_datetime(notice.effective_end)
        if start_dt is not None:
            start_values.append(start_dt)
        if end_dt is not None:
            end_values.append(end_dt)

    top_locations = [
        {"label": label, "count": count}
        for label, count in location_counts.most_common(5)
    ]
    top_classifications = [
        {"label": label, "count": count}
        for label, count in classification_counts.most_common(5)
    ]

    representative_notices = [
        {
            "notice_id": notice.notice_id,
            "location": notice.location,
            "classification": notice.classification,
            "text": notice.text[:240],
            "effective_start": notice.effective_start,
            "effective_end": notice.effective_end,
            "is_alert": _notam_is_alert(notice),
            "is_restricted": _notam_is_restricted(notice),
            "duration_hours": _notam_effective_window_hours(notice),
            "country_hint": _infer_location_hint(notice.location)[0],
            "region_hint": _explicit_region_hint(notice) or _infer_location_hint(notice.location)[1],
        }
        for notice in condensed_notices
    ]

    return {
        "raw_notice_count": len(notices),
        "condensed_notice_count": len(condensed_notices),
        "alert_notice_count": sum(1 for notice in notices if _notam_is_alert(notice)),
        "restricted_notice_count": sum(1 for notice in notices if _notam_is_restricted(notice)),
        "top_locations": top_locations,
        "top_classifications": top_classifications,
        "inferred_countries": [
            {"label": label, "count": count}
            for label, count in country_counts.most_common(5)
        ],
        "inferred_regions": [
            {"label": label, "count": count}
            for label, count in region_counts.most_common(5)
        ],
        "effective_window_start": min(start_values).isoformat() if start_values else None,
        "effective_window_end": max(end_values).isoformat() if end_values else None,
        "representative_notices": representative_notices,
    }


def build_assessment_prompt(notices: Sequence[NotamNotice]) -> str:
    condensed_notices = build_condensed_notam_notices(notices)
    context = _build_context(notices, condensed_notices)
    return PROMPT_TEMPLATE.format(context_json=json.dumps(context, indent=2))


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


def _build_freshness_score(notices: Sequence[NotamNotice]) -> float:
    if not notices:
        return 0.0

    recent_window_count = 0
    short_window_count = 0
    for notice in notices:
        window_hours = _notam_effective_window_hours(notice)
        if window_hours is None:
            continue
        if window_hours <= 72:
            recent_window_count += 1
        if window_hours <= 24:
            short_window_count += 1
    return round(
        min(
            1.0,
            (recent_window_count / len(notices)) * 0.6
            + (short_window_count / len(notices)) * 0.4,
        ),
        4,
    )


def _build_error_assessment(
    *,
    explanation: str,
    assessed_notice_count: int,
    freshness_score: float,
) -> NotamSignalAssessment:
    return NotamSignalAssessment(
        status="error",
        prompt_version=PROMPT_VERSION,
        probability_percent=None,
        target_region=None,
        target_country=None,
        summary=explanation,
        assessed_notice_count=assessed_notice_count,
        freshness_score=freshness_score,
    )


def _build_disabled_assessment(
    *,
    explanation: str,
    assessed_notice_count: int,
    freshness_score: float,
) -> NotamSignalAssessment:
    return NotamSignalAssessment(
        status="disabled",
        prompt_version=PROMPT_VERSION,
        probability_percent=None,
        target_region=None,
        target_country=None,
        summary=explanation,
        assessed_notice_count=assessed_notice_count,
        freshness_score=freshness_score,
    )


class NotamStrikeAssessmentService:
    def __init__(
        self,
        config: NotamAssessmentConfig,
        request_sender: Callable[[Request, int], dict[str, Any]] | None = None,
    ) -> None:
        self._config = config
        self._request_sender = request_sender or self._send_request

    def assess_notices(self, notices: Sequence[NotamNotice]) -> NotamSignalAssessment:
        condensed_notices = build_condensed_notam_notices(notices)
        freshness_score = _build_freshness_score(condensed_notices)

        if not condensed_notices:
            return NotamSignalAssessment(
                status="ready",
                prompt_version=PROMPT_VERSION,
                probability_percent=0,
                target_region=None,
                target_country=None,
                summary="No parseable NOTAM notices were available in the stored snapshot.",
                assessed_notice_count=0,
                freshness_score=0.0,
            )

        if not self._config.api_key or not self._config.model:
            return _build_disabled_assessment(
                explanation=(
                    "AI assessment is disabled because NOTAM_AI_API_KEY or "
                    "NOTAM_AI_MODEL is not configured."
                ),
                assessed_notice_count=len(condensed_notices),
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
                                "You analyze NOTAM clusters for military escalation and strike-preparation indicators."
                            ),
                        },
                        {
                            "role": "user",
                            "content": build_assessment_prompt(condensed_notices),
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
                "NOTAM AI upstream returned HTTP %s: %s",
                status_code,
                _truncate_debug_text(response_body or exc.reason),
            )
            return _build_error_assessment(
                explanation=f"AI request failed with HTTP {status_code} from the upstream model provider.",
                assessed_notice_count=len(condensed_notices),
                freshness_score=freshness_score,
            )
        except TimeoutError:
            logger.warning(
                "NOTAM AI request timed out after %s seconds",
                self._config.timeout_seconds,
            )
            return _build_error_assessment(
                explanation="AI request timed out while waiting for the upstream model provider.",
                assessed_notice_count=len(condensed_notices),
                freshness_score=freshness_score,
            )
        except URLError as exc:
            logger.warning(
                "NOTAM AI request could not reach upstream provider: %s",
                _truncate_debug_text(exc.reason),
            )
            return _build_error_assessment(
                explanation="AI request failed to reach the upstream model provider.",
                assessed_notice_count=len(condensed_notices),
                freshness_score=freshness_score,
            )
        except OSError as exc:
            logger.warning(
                "NOTAM AI request failed with OS error: %s",
                _truncate_debug_text(exc),
            )
            return _build_error_assessment(
                explanation="AI request could not be completed because of a local network or transport error.",
                assessed_notice_count=len(condensed_notices),
                freshness_score=freshness_score,
            )

        try:
            response_content = _extract_message_content(payload)
            parsed = _parse_assessment_json(response_content)
        except ValueError as exc:
            logger.warning(
                "NOTAM AI response could not be parsed as required JSON: %s; payload=%s",
                exc,
                _truncate_debug_text(json.dumps(payload, ensure_ascii=True)),
            )
            return _build_error_assessment(
                explanation="AI response could not be parsed as the required JSON object.",
                assessed_notice_count=len(condensed_notices),
                freshness_score=freshness_score,
            )

        probability = parsed.get("probability_percent")
        target_region = parsed.get("target_region")
        target_country = parsed.get("target_country")
        summary = parsed.get("summary")
        valid = (
            isinstance(probability, int)
            and 0 <= probability <= 100
            and (target_region is None or isinstance(target_region, str))
            and (target_country is None or isinstance(target_country, str))
            and isinstance(summary, str)
            and bool(summary.strip())
        )
        if not valid:
            logger.warning(
                "NOTAM AI response JSON did not match required fields: %s",
                _truncate_debug_text(json.dumps(parsed, ensure_ascii=True)),
            )
            return _build_error_assessment(
                explanation=(
                    "AI response JSON did not match the required fields: "
                    "probability_percent, target_region, target_country, summary."
                ),
                assessed_notice_count=len(condensed_notices),
                freshness_score=freshness_score,
            )

        return NotamSignalAssessment(
            status="ready",
            prompt_version=PROMPT_VERSION,
            probability_percent=probability,
            target_region=target_region.strip() if isinstance(target_region, str) and target_region.strip() else None,
            target_country=target_country.strip() if isinstance(target_country, str) and target_country.strip() else None,
            summary=summary.strip(),
            assessed_notice_count=len(condensed_notices),
            freshness_score=freshness_score,
        )

    @staticmethod
    def _send_request(request: Request, timeout_seconds: int) -> dict[str, Any]:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def probability_to_signal_feature(assessment: NotamSignalAssessment) -> float:
    if assessment.status != "ready" or assessment.probability_percent is None:
        return 0.0
    return round(assessment.probability_percent / 100.0, 4)


def derive_region_focus_from_assessment(
    assessment: NotamSignalAssessment, fallback: str
) -> str:
    if assessment.status != "ready":
        return fallback
    if assessment.target_country:
        return assessment.target_country
    if assessment.target_region:
        return assessment.target_region
    return fallback
