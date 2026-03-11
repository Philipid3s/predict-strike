from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.collectors.opensky import OpenSkyAnomalyAssessment
from src.models.schemas import OpenSkyStrikeAssessment


logger = logging.getLogger(__name__)

PROMPT_VERSION = "opensky-strike-v2"
DEFAULT_AI_API_URL = "https://api.openai.com/v1/chat/completions"

PROMPT_TEMPLATE = """Role: You are a Military Intelligence Analyst specializing in Aerial OSINT.

Task: Analyze the provided OpenSky data to identify "Strike Indicators" in non-NATO/non-Allied regions.

1. Exclusion Logic:
Ignore any aircraft currently operating within the sovereign airspace or routine training ranges of the US, NATO members, Japan, and South Korea, UNLESS they are observed transiting toward a high-tension border (for example, crossing into the Middle East or Eastern Europe).

2. Strike Package Assessment:
Look for the "Strike Stack." Rank the probability of a coordinated operation based on the presence of these roles in the same geographic cluster:

Primary Indicator (Tankers): Multiple KC-135, KC-46, or A330 MRTT callsigns in holding patterns/orbits.

Secondary Indicator (AWACS/ISR): E-3 Sentry, E-8 JSTARS, or RQ-4 Global Hawk (FORTE/HOMER callsigns) patrolling the perimeter.

Support Indicator (C2/ELINT): RC-135 (RIVET JOINT) or similar signal-intelligence platforms.

3. Analysis Output:

Targeted Region: Identify the specific country or border under observation.

Strike Probability: (0-100%) based on the "Strike Stack" density.

Movement Trend: Are these assets newly arrived in the last 6-12 hours, or is this a persistent 24/7 presence?

Anomaly Note: Highlight any "dark" aircraft (transponders turned off mid-flight) or unusual callsign changes.

Return only valid JSON with this exact shape:
{{
  "probability_percent": 0,
  "countries": ["country name"],
  "explanation": "short explanation"
}}

Anomalous flights:
{flights_json}
"""


@dataclass(frozen=True)
class OpenSkyAssessmentConfig:
    api_url: str | None
    api_key: str | None
    model: str | None
    timeout_seconds: int = 15


def _truncate_debug_text(value: Any, *, limit: int = 500) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _format_position(assessment: OpenSkyAnomalyAssessment) -> dict[str, float | None]:
    return {
        "latitude": assessment.state.latitude,
        "longitude": assessment.state.longitude,
    }


def build_condensed_anomaly_list(
    assessments: Sequence[OpenSkyAnomalyAssessment],
) -> list[dict[str, Any]]:
    return [
        {
            "callsign": assessment.state.callsign,
            "icao24": assessment.state.icao24,
            "position": _format_position(assessment),
        }
        for assessment in assessments
    ]


def build_assessment_prompt(assessments: Sequence[OpenSkyAnomalyAssessment]) -> str:
    return PROMPT_TEMPLATE.format(
        flights_json=json.dumps(build_condensed_anomaly_list(assessments), indent=2)
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


class OpenSkyStrikeAssessmentService:
    def __init__(
        self,
        config: OpenSkyAssessmentConfig,
        request_sender: Callable[[Request, int], dict[str, Any]] | None = None,
    ) -> None:
        self._config = config
        self._request_sender = request_sender or self._send_request

    def assess_anomalies(
        self, assessments: Sequence[OpenSkyAnomalyAssessment]
    ) -> OpenSkyStrikeAssessment:
        if not assessments:
            return OpenSkyStrikeAssessment(
                status="ready",
                prompt_version=PROMPT_VERSION,
                probability_percent=0,
                countries=[],
                explanation="No anomalous OpenSky flights were present in the latest snapshot.",
            )

        if not self._config.api_key or not self._config.model:
            return OpenSkyStrikeAssessment(
                status="disabled",
                prompt_version=PROMPT_VERSION,
                probability_percent=None,
                countries=[],
                explanation=(
                    "AI assessment is disabled because OPENSKY_AI_API_KEY or "
                    "OPENSKY_AI_MODEL is not configured."
                ),
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
                                "You analyze unusual aircraft traffic for geopolitical and "
                                "military warning indicators."
                            ),
                        },
                        {
                            "role": "user",
                            "content": build_assessment_prompt(assessments),
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
                "OpenSky AI upstream returned HTTP %s: %s",
                status_code,
                _truncate_debug_text(response_body or exc.reason),
            )
            return self._build_error_assessment(
                f"AI request failed with HTTP {status_code} from the upstream model provider."
            )
        except TimeoutError:
            logger.warning("OpenSky AI request timed out after %s seconds", self._config.timeout_seconds)
            return self._build_error_assessment(
                "AI request timed out while waiting for the upstream model provider."
            )
        except URLError as exc:
            logger.warning(
                "OpenSky AI request could not reach upstream provider: %s",
                _truncate_debug_text(exc.reason),
            )
            return self._build_error_assessment(
                "AI request failed to reach the upstream model provider."
            )
        except OSError as exc:
            logger.warning(
                "OpenSky AI request failed with OS error: %s",
                _truncate_debug_text(exc),
            )
            return self._build_error_assessment(
                "AI request could not be completed because of a local network or transport error."
            )

        try:
            response_content = _extract_message_content(payload)
            parsed = _parse_assessment_json(response_content)
        except ValueError as exc:
            logger.warning(
                "OpenSky AI response could not be parsed as required JSON: %s; payload=%s",
                exc,
                _truncate_debug_text(json.dumps(payload, ensure_ascii=True)),
            )
            return self._build_error_assessment(
                "AI response could not be parsed as the required JSON object."
            )

        probability = parsed.get("probability_percent")
        countries = parsed.get("countries")
        explanation = parsed.get("explanation")
        if not isinstance(probability, int):
            raise_assessment_error = True
        else:
            raise_assessment_error = not 0 <= probability <= 100
        if (
            raise_assessment_error
            or not isinstance(countries, list)
            or not all(isinstance(country, str) for country in countries)
            or not isinstance(explanation, str)
            or not explanation.strip()
        ):
            logger.warning(
                "OpenSky AI response JSON did not match required fields: %s",
                _truncate_debug_text(json.dumps(parsed, ensure_ascii=True)),
            )
            return self._build_error_assessment(
                "AI response JSON did not match the required fields: probability_percent, countries, explanation."
            )

        return OpenSkyStrikeAssessment(
            status="ready",
            prompt_version=PROMPT_VERSION,
            probability_percent=probability,
            countries=[country.strip() for country in countries if country.strip()],
            explanation=explanation.strip(),
        )

    @staticmethod
    def _build_error_assessment(explanation: str) -> OpenSkyStrikeAssessment:
        return OpenSkyStrikeAssessment(
            status="error",
            prompt_version=PROMPT_VERSION,
            probability_percent=None,
            countries=[],
            explanation=explanation,
        )

    @staticmethod
    def _send_request(request: Request, timeout_seconds: int) -> dict[str, Any]:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def probability_to_signal_feature(assessment: OpenSkyStrikeAssessment) -> float:
    if assessment.status != "ready" or assessment.probability_percent is None:
        return 0.0
    return round(assessment.probability_percent / 100.0, 4)


def derive_region_focus_from_assessment(
    assessment: OpenSkyStrikeAssessment, fallback: str
) -> str:
    if assessment.status != "ready" or not assessment.countries:
        return fallback
    return ", ".join(assessment.countries)
