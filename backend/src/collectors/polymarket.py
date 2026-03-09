from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, Callable
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_POLYMARKET_GAMMA_BASE_URL = "https://gamma-api.polymarket.com/"
DEFAULT_POLYMARKET_EVENTS_PATH = "events?active=true&closed=false&limit=50"
DEFAULT_PIZZINT_POLYMARKET_BREAKING_URL = (
    "https://www.pizzint.watch/api/markets/breaking?window=6h&final_limit=20&format=ticker"
)
DEFAULT_REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
}
GEOPOLITICAL_KEYWORDS = (
    "AIRSPACE",
    "CONFLICT",
    "MILITARY",
    "MISSILE",
    "MOBILIZATION",
    "NATO",
    "SANCTION",
    "STRIKE",
    "TROOPS",
    "WAR",
)
BOOTSTRAP_POLYMARKET_RESPONSE: dict[str, Any] = {
    "events": [
        {
            "id": "poly-event-1",
            "title": "Middle East Escalation",
            "volume24hr": 182340.0,
            "markets": [
                {
                    "id": "poly-market-1",
                    "question": "Will a major cross-border strike occur in the Middle East within 30 days?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.43", "0.57"]',
                    "volume": 182340.0,
                }
            ],
        },
        {
            "id": "poly-event-2",
            "title": "Airspace Restrictions",
            "volume24hr": 95420.0,
            "markets": [
                {
                    "id": "poly-market-2",
                    "question": "Will emergency airspace restrictions expand before next week?",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": ["0.58", "0.42"],
                    "volume24hr": 95420.0,
                }
            ],
        },
        {
            "id": "poly-event-3",
            "title": "Unrelated Market",
            "volume24hr": 1000.0,
            "markets": [
                {
                    "id": "poly-market-3",
                    "question": "Will a tech company beat earnings this quarter?",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": ["0.71", "0.29"],
                    "volume": 1000.0,
                }
            ],
        },
    ]
}


@dataclass(frozen=True)
class PolymarketMarket:
    market_id: str
    question: str
    market_probability: float
    volume: float


@dataclass(frozen=True)
class PolymarketObservation:
    collected_at: datetime
    status: str
    upstream: str
    raw_payload: Any
    markets: list[PolymarketMarket]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return loaded if isinstance(loaded, list) else []
    return []


def _event_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload.get("events"), list):
        return payload["events"]
    if isinstance(payload.get("items"), list):
        return payload["items"]
    if isinstance(payload.get("results"), list):
        return payload["results"]
    if isinstance(payload.get("markets"), list):
        return [{"id": "markets-root", "title": "", "markets": payload["markets"]}]
    return []


def _extract_market_probability(row: dict[str, Any]) -> float | None:
    direct_probability = _coerce_float(
        row.get("probability")
        or row.get("currentPrice")
        or row.get("lastTradePrice")
        or row.get("lastPrice")
        or row.get("latest_price")
    )
    if direct_probability is not None:
        return direct_probability

    outcomes = _coerce_sequence(row.get("outcomes"))
    outcome_prices = _coerce_sequence(
        row.get("outcomePrices") or row.get("outcome_prices")
    )
    if not outcome_prices:
        return None

    if outcomes:
        for index, outcome in enumerate(outcomes):
            if str(outcome).strip().lower() == "yes" and index < len(outcome_prices):
                return _coerce_float(outcome_prices[index])
    return _coerce_float(outcome_prices[0])


def _is_geopolitical(text: str) -> bool:
    haystack = text.upper()
    return any(keyword in haystack for keyword in GEOPOLITICAL_KEYWORDS)


def parse_markets(payload: Any) -> list[PolymarketMarket]:
    parsed: list[tuple[PolymarketMarket, bool]] = []
    for event in _event_rows(payload):
        event_title = str(event.get("title") or event.get("question") or "")
        event_is_geo = _is_geopolitical(event_title)
        for market_row in event.get("markets") or []:
            question = str(
                market_row.get("question") or market_row.get("title") or event_title
            ).strip()
            probability = _extract_market_probability(market_row)
            if probability is None:
                continue
            volume = _coerce_float(
                market_row.get("volume")
                or market_row.get("volume24h")
                or market_row.get("volume24hr")
                or event.get("volume")
                or event.get("volume24h")
                or event.get("volume24hr")
            )
            parsed.append(
                (
                    PolymarketMarket(
                        market_id=str(
                            market_row.get("id")
                            or market_row.get("market_id")
                            or market_row.get("conditionId")
                            or market_row.get("slug")
                            or question
                        ),
                        question=question,
                        market_probability=probability,
                        volume=round(volume or 0.0, 4),
                    ),
                    event_is_geo or _is_geopolitical(question),
                )
            )

    geopolitical_markets = [market for market, is_geo in parsed if is_geo]
    if geopolitical_markets:
        return geopolitical_markets
    return [market for market, _ in parsed]


class PolymarketCollector:
    def __init__(
        self,
        source_url: str | None = None,
        payload_loader: Callable[[], dict[str, Any]] | None = None,
        pizzint_payload_loader: Callable[[], dict[str, Any]] | None = None,
        pizzint_breaking_url: str = DEFAULT_PIZZINT_POLYMARKET_BREAKING_URL,
        fallback_payload: dict[str, Any] | None = None,
    ) -> None:
        self._source_url = normalize_source_url(
            source_url or DEFAULT_POLYMARKET_GAMMA_BASE_URL
        )
        self._payload_loader = payload_loader or self._load_live_payload
        self._pizzint_breaking_url = pizzint_breaking_url
        self._pizzint_payload_loader = (
            pizzint_payload_loader or self._load_pizzint_breaking_payload
        )
        self._fallback_payload = fallback_payload or BOOTSTRAP_POLYMARKET_RESPONSE

    def fetch_observation(self) -> PolymarketObservation:
        try:
            payload = self._payload_loader()
            status = "active"
            upstream = "gamma"
        except Exception:
            try:
                payload = self._pizzint_payload_loader()
                upstream = "pizzint"
            except Exception:
                payload = self._fallback_payload
                upstream = "bootstrap"
            status = "degraded"

        return PolymarketObservation(
            collected_at=_utc_now(),
            status=status,
            upstream=upstream,
            raw_payload=payload,
            markets=parse_markets(payload),
        )

    def _load_live_payload(self) -> dict[str, Any]:
        request = Request(self._source_url, headers=DEFAULT_REQUEST_HEADERS)
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    def _load_pizzint_breaking_payload(self) -> dict[str, Any]:
        request = Request(self._pizzint_breaking_url, headers=DEFAULT_REQUEST_HEADERS)
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))


def normalize_source_url(source_url: str) -> str:
    normalized = source_url.strip()
    if not normalized:
        return f"{DEFAULT_POLYMARKET_GAMMA_BASE_URL}{DEFAULT_POLYMARKET_EVENTS_PATH}"

    lower_normalized = normalized.lower()
    if "events" in lower_normalized or "markets" in lower_normalized or "?" in normalized:
        return normalized

    if not normalized.endswith("/"):
        normalized = f"{normalized}/"
    return f"{normalized}{DEFAULT_POLYMARKET_EVENTS_PATH}"
