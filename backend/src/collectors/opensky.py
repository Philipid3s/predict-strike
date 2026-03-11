from dataclasses import dataclass
from datetime import UTC, datetime
import json
from math import cos, floor, radians, sqrt
from typing import Any, Callable, Sequence
from urllib.request import urlopen

from src.config.opensky_registry import US_NATO_MILITARY_AIRFIELDS


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
TANKER_TRANSPORT_CALLSIGN_PREFIXES = (
    "ASCOT",
    "RCH",
    "RRR",
)
REGION_BUCKET_DEGREES = 6.0
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


@dataclass(frozen=True)
class OpenSkyAnomalyAssessment:
    state: OpenSkyState
    reasons: tuple[str, ...]


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


def is_tanker_transport_like(state: OpenSkyState) -> bool:
    if not state.callsign:
        return False
    return state.callsign.upper().startswith(TANKER_TRANSPORT_CALLSIGN_PREFIXES)


def _region_bucket_key(
    latitude: float, longitude: float
) -> tuple[float, float, float, float]:
    lat_min = floor(latitude / REGION_BUCKET_DEGREES) * REGION_BUCKET_DEGREES
    lon_min = floor(longitude / REGION_BUCKET_DEGREES) * REGION_BUCKET_DEGREES
    return (
        lat_min,
        lat_min + REGION_BUCKET_DEGREES,
        lon_min,
        lon_min + REGION_BUCKET_DEGREES,
    )


def _format_axis_range(axis_min: float, axis_max: float, positive_suffix: str, negative_suffix: str) -> str:
    suffix = positive_suffix if axis_min >= 0 else negative_suffix
    start = abs(int(axis_min))
    end = abs(int(axis_max))
    return f"{start}-{end}{suffix}"


def format_region_bucket(bucket: tuple[float, float, float, float]) -> str:
    lat_min, lat_max, lon_min, lon_max = bucket
    return (
        f"{_format_axis_range(lat_min, lat_max, 'N', 'S')} / "
        f"{_format_axis_range(lon_min, lon_max, 'E', 'W')} sector"
    )


def _is_in_bucket(
    state: OpenSkyState, bucket: tuple[float, float, float, float]
) -> bool:
    if state.latitude is None or state.longitude is None:
        return False
    lat_min, lat_max, lon_min, lon_max = bucket
    return (
        lat_min <= state.latitude < lat_max and lon_min <= state.longitude < lon_max
    )


def _counts_toward_region_focus(state: OpenSkyState) -> bool:
    return is_military_like(state) or is_tanker_transport_like(state)


def dominant_suspicious_region_bucket(
    states: Sequence[OpenSkyState],
) -> tuple[float, float, float, float] | None:
    bucket_counts: dict[tuple[float, float, float, float], int] = {}
    for state in states:
        if not _counts_toward_region_focus(state):
            continue
        if state.latitude is None or state.longitude is None:
            continue
        bucket = _region_bucket_key(state.latitude, state.longitude)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    if not bucket_counts:
        return None

    bucket, count = max(bucket_counts.items(), key=lambda item: (item[1], item[0][0], item[0][2]))
    if count < 3:
        return None
    return bucket


def dominant_suspicious_region_name(states: Sequence[OpenSkyState]) -> str | None:
    bucket = dominant_suspicious_region_bucket(states)
    if bucket is None:
        return None
    return format_region_bucket(bucket)


def _distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    lat_scale = 111.0
    lon_scale = 111.0 * cos(radians((latitude_a + latitude_b) / 2))
    delta_lat = (latitude_a - latitude_b) * lat_scale
    delta_lon = (longitude_a - longitude_b) * lon_scale
    return sqrt((delta_lat * delta_lat) + (delta_lon * delta_lon))


def departure_airfield_name(state: OpenSkyState) -> str | None:
    if state.latitude is None or state.longitude is None:
        return None
    if (state.baro_altitude or 0.0) > 4000.0 or (state.velocity or 0.0) < 120.0:
        return None

    for airfield in US_NATO_MILITARY_AIRFIELDS:
        distance_km = _distance_km(
            state.latitude,
            state.longitude,
            airfield.latitude,
            airfield.longitude,
        )
        if distance_km <= 40.0:
            return airfield.name
    return None


def military_cluster_size(states: Sequence[OpenSkyState]) -> int:
    return sum(1 for state in states if is_military_like(state))


def assess_opensky_anomalies(states: Sequence[OpenSkyState]) -> list[OpenSkyAnomalyAssessment]:
    cluster_size = military_cluster_size(states)
    dominant_region_bucket = dominant_suspicious_region_bucket(states)
    dominant_region_name = format_region_bucket(dominant_region_bucket) if dominant_region_bucket is not None else None
    assessments: list[OpenSkyAnomalyAssessment] = []

    for state in states:
        reasons: list[str] = []
        if is_military_like(state):
            reasons.append("military_like_callsign")
        if is_tanker_transport_like(state):
            reasons.append("tanker_transport_pattern")
        if (
            dominant_region_bucket is not None
            and dominant_region_name is not None
            and _counts_toward_region_focus(state)
            and _is_in_bucket(state, dominant_region_bucket)
        ):
            reasons.append(f"suspicious_region_concentration:{dominant_region_name}")
        airfield_name = departure_airfield_name(state)
        if airfield_name is not None:
            reasons.append(f"military_airfield_departure:{airfield_name}")
        if cluster_size >= 2 and is_military_like(state):
            reasons.append("military_callsign_cluster")
        if reasons:
            assessments.append(OpenSkyAnomalyAssessment(state=state, reasons=tuple(reasons)))

    return assessments


def compute_flight_anomaly(states: Sequence[OpenSkyState]) -> float:
    assessments = assess_opensky_anomalies(states)
    if not assessments:
        return 0.0

    military_count = sum(
        1 for assessment in assessments if "military_like_callsign" in assessment.reasons
    )
    tanker_count = sum(
        1 for assessment in assessments if "tanker_transport_pattern" in assessment.reasons
    )
    departure_count = sum(
        1
        for assessment in assessments
        if any(reason.startswith("military_airfield_departure:") for reason in assessment.reasons)
    )
    regional_count = sum(
        1
        for assessment in assessments
        if any(reason.startswith("suspicious_region_concentration:") for reason in assessment.reasons)
    )

    score = 0.0
    score += min(military_count, 4) * 0.07
    score += min(tanker_count, 3) * 0.03
    score += min(departure_count, 2) * 0.10

    if military_count >= 2:
        score += 0.06 + (min(military_count, 4) - 2) * 0.02

    if regional_count >= 3:
        score += 0.08 + (min(regional_count, 5) - 3) * 0.02

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
