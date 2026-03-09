from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, Callable, Sequence
from urllib.request import urlopen


OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
DEFAULT_TIMEOUT_SECONDS = 10
MILITARY_CALLSIGN_PREFIXES = (
    "ASCOT",
    "DUKE",
    "FORTE",
    "MMF",
    "NATO",
    "QID",
    "RCH",
    "RRR",
)
BOOTSTRAP_OPENSKY_RESPONSE: dict[str, Any] = {
    "time": 1772861400,
    "states": [
        [
            "abc123",
            "RCH123  ",
            "United States",
            None,
            1772861340,
            32.85,
            44.12,
            9750.0,
            False,
            215.0,
            181.0,
            0.0,
            None,
            10100.0,
            "7000",
            False,
            0,
        ],
        [
            "def456",
            "NATO45  ",
            "Luxembourg",
            None,
            1772861344,
            33.10,
            43.80,
            10450.0,
            False,
            236.0,
            95.0,
            0.0,
            None,
            10620.0,
            "2201",
            False,
            0,
        ],
        [
            "ghi789",
            "AAL102  ",
            "United States",
            None,
            1772861335,
            39.85,
            -84.10,
            11000.0,
            False,
            250.0,
            89.0,
            0.0,
            None,
            11250.0,
            "4452",
            False,
            0,
        ],
        [
            "jkl012",
            "DAL220  ",
            "United States",
            None,
            1772861322,
            38.91,
            -77.04,
            9200.0,
            False,
            190.0,
            140.0,
            0.0,
            None,
            9350.0,
            "4312",
            False,
            0,
        ],
    ],
}


@dataclass(frozen=True)
class OpenSkyState:
    icao24: str
    callsign: str | None
    origin_country: str | None
    longitude: float | None
    latitude: float | None
    baro_altitude: float | None
    velocity: float | None
    geo_altitude: float | None


@dataclass(frozen=True)
class OpenSkyObservation:
    collected_at: datetime
    status: str
    raw_payload: dict[str, Any]
    states: list[OpenSkyState]
    flight_anomaly: float


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _parse_state(row: Sequence[Any]) -> OpenSkyState:
    return OpenSkyState(
        icao24=str(row[0]),
        callsign=str(row[1]).strip() if row[1] else None,
        origin_country=str(row[2]) if row[2] else None,
        longitude=_coerce_float(row[5]),
        latitude=_coerce_float(row[6]),
        baro_altitude=_coerce_float(row[7]),
        velocity=_coerce_float(row[9]),
        geo_altitude=_coerce_float(row[13]),
    )


def parse_states(payload: dict[str, Any]) -> list[OpenSkyState]:
    rows = payload.get("states") or []
    return [_parse_state(row) for row in rows if len(row) >= 14]


def is_military_like(state: OpenSkyState) -> bool:
    if not state.callsign:
        return False
    return state.callsign.upper().startswith(MILITARY_CALLSIGN_PREFIXES)


def compute_flight_anomaly(states: Sequence[OpenSkyState]) -> float:
    military_like = sum(1 for state in states if is_military_like(state))
    elevated_activity = sum(
        1
        for state in states
        if (state.velocity or 0.0) >= 180.0 and (state.baro_altitude or 0.0) >= 9000.0
    )
    score = (military_like * 0.22) + (min(elevated_activity, 6) * 0.04)
    return round(min(score, 1.0), 4)


class OpenSkyCollector:
    def __init__(
        self,
        payload_loader: Callable[[], dict[str, Any]] | None = None,
        fallback_payload: dict[str, Any] | None = None,
    ) -> None:
        self._payload_loader = payload_loader or self._load_live_payload
        self._fallback_payload = fallback_payload or BOOTSTRAP_OPENSKY_RESPONSE

    def fetch_observation(self) -> OpenSkyObservation:
        try:
            payload = self._payload_loader()
            status = "active"
        except Exception:
            payload = self._fallback_payload
            status = "degraded"

        states = parse_states(payload)
        return OpenSkyObservation(
            collected_at=_utc_now(),
            status=status,
            raw_payload=payload,
            states=states,
            flight_anomaly=compute_flight_anomaly(states),
        )

    def _load_live_payload(self) -> dict[str, Any]:
        with urlopen(OPENSKY_STATES_URL, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
