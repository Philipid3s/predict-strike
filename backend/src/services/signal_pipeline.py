from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.collectors.gdelt import GdeltCollector
from src.collectors.notam import NotamCollector
from src.collectors.opensky import OpenSkyCollector
from src.config.settings import get_settings
from src.models.schemas import FeatureSet, LatestSignalsResponse, SignalSource
from src.storage.signal_store import SignalStore


BASELINE_FEATURES = FeatureSet(
    flight_anomaly=0.25,
    notam_spike=0.42,
    satellite_buildup=0.37,
    news_volume=0.61,
    osint_activity=0.49,
    pizza_index=0.18,
)


STATIC_BASELINE_SOURCE_NAMES = (
    "Satellite Monitoring",
    "Social OSINT",
    "Pizza Index Activity",
)


@dataclass(frozen=True)
class CollectedSourceObservation:
    source_name: str
    collected_at: datetime
    status: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class CollectedSignalInputs:
    generated_at: datetime
    region_focus: str
    flight_anomaly: float
    notam_spike: float
    news_volume: float
    sources: list[SignalSource]
    observations: list[CollectedSourceObservation]


def _mode_from_source_status(status: str) -> str:
    return "live" if status == "active" else "fallback"


def _static_baseline_sources() -> list[SignalSource]:
    return [
        SignalSource(name=name, status="planned", mode="static_baseline", last_checked_at=None)
        for name in STATIC_BASELINE_SOURCE_NAMES
    ]


def _snapshot_matches_current_contract(snapshot: LatestSignalsResponse) -> bool:
    source_names = {source.name for source in snapshot.sources}
    return (
        all(name in source_names for name in STATIC_BASELINE_SOURCE_NAMES)
        and "Polymarket" not in source_names
    )


def build_snapshot_from_sources() -> LatestSignalsResponse:
    return _snapshot_from_inputs(_collect_signal_inputs())


def _collect_signal_inputs() -> CollectedSignalInputs:
    settings = get_settings()
    opensky_observation = OpenSkyCollector().fetch_observation()
    notam_observation = NotamCollector(
        source_url=settings.notam_source_url
    ).fetch_observation()
    gdelt_observation = GdeltCollector(
        source_url=settings.gdelt_source_url
    ).fetch_observation()
    generated_at = max(
        opensky_observation.collected_at,
        notam_observation.collected_at,
        gdelt_observation.collected_at,
    )
    return CollectedSignalInputs(
        generated_at=generated_at,
        region_focus=settings.default_region_focus,
        flight_anomaly=opensky_observation.flight_anomaly,
        notam_spike=notam_observation.notam_spike,
        news_volume=gdelt_observation.news_volume,
        sources=[
            SignalSource(
                name="OpenSky Network",
                status=opensky_observation.status,
                mode=_mode_from_source_status(opensky_observation.status),
                last_checked_at=opensky_observation.collected_at,
            ),
            SignalSource(
                name="NOTAM Feed",
                status=notam_observation.status,
                mode=_mode_from_source_status(notam_observation.status),
                last_checked_at=notam_observation.collected_at,
            ),
            SignalSource(
                name="GDELT",
                status=gdelt_observation.status,
                mode=_mode_from_source_status(gdelt_observation.status),
                last_checked_at=gdelt_observation.collected_at,
            ),
            *_static_baseline_sources(),
        ],
        observations=[
            CollectedSourceObservation(
                source_name="OpenSky Network",
                collected_at=opensky_observation.collected_at,
                status=opensky_observation.status,
                payload=opensky_observation.raw_payload,
            ),
            CollectedSourceObservation(
                source_name="NOTAM Feed",
                collected_at=notam_observation.collected_at,
                status=notam_observation.status,
                payload=notam_observation.raw_payload,
            ),
            CollectedSourceObservation(
                source_name="GDELT",
                collected_at=gdelt_observation.collected_at,
                status=gdelt_observation.status,
                payload=gdelt_observation.raw_payload,
            ),
        ],
    )


def _snapshot_from_inputs(inputs: CollectedSignalInputs) -> LatestSignalsResponse:
    return LatestSignalsResponse(
        generated_at=inputs.generated_at,
        region_focus=inputs.region_focus,
        features=BASELINE_FEATURES.model_copy(
            update={
                "flight_anomaly": inputs.flight_anomaly,
                "notam_spike": inputs.notam_spike,
                "news_volume": inputs.news_volume,
            }
        ),
        sources=inputs.sources,
    )


def refresh_latest_snapshot() -> LatestSignalsResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    inputs = _collect_signal_inputs()
    for observation in inputs.observations:
        store.save_source_observation(
            source_name=observation.source_name,
            collected_at=observation.collected_at,
            status=observation.status,
            payload=observation.payload,
        )
    snapshot = _snapshot_from_inputs(inputs)
    return store.save_signal_snapshot(snapshot)


def get_or_create_latest_snapshot() -> LatestSignalsResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    snapshot = store.get_latest_signal_snapshot()
    if snapshot is not None and _snapshot_matches_current_contract(snapshot):
        return snapshot
    return refresh_latest_snapshot()
