from dataclasses import dataclass
from datetime import UTC, datetime
from collections import Counter
from typing import Any

from src.collectors.gdelt import (
    GDELT_ALERT_KEYWORDS,
    GdeltCollector,
    article_source_label,
    compute_news_volume,
    extract_article_regions,
    extract_article_themes,
    is_alert_article,
    parse_articles,
)
from src.collectors.notam import (
    NOTAM_ALERT_KEYWORDS,
    NotamCollector,
    NotamNotice,
    NotamObservation,
    compute_notam_spike,
    parse_notices,
)
from src.collectors.opensky import (
    OpenSkyCollector,
    assess_opensky_anomalies,
    dominant_suspicious_region_name,
    parse_states,
)
from src.config.notam_location_registry import resolve_notam_location_context
from src.config.settings import get_settings
from src.models.schemas import (
    FeatureSet,
    GdeltCountBreakdown,
    GdeltDetailResponse,
    GdeltHeadline,
    GdeltProvenance,
    GdeltSignalAssessment,
    GdeltSignalRefreshResponse,
    LatestSignalsResponse,
    NotamCountBreakdown,
    NotamDetailResponse,
    NotamNoticeSummary,
    NotamSignalAssessment,
    NotamSignalRefreshResponse,
    OpenSkyAnomaliesResponse,
    OpenSkyAnomaly,
    OpenSkySignalRefreshResponse,
    OpenSkyStrikeAssessment,
    PizzaIndexSnapshotResponse,
    SignalSource,
    SignalSourceRefreshResponse,
)
from src.services.gdelt_assessment import (
    GdeltAssessmentConfig,
    GdeltStrikeAssessmentService,
    build_signal_article_set,
    compute_article_freshness_score,
    derive_region_focus_from_assessment as derive_gdelt_region_focus_from_assessment,
    filter_recent_articles,
    is_action_indicative_article,
    is_us_nato_actor_article,
    probability_to_signal_feature as gdelt_probability_to_signal_feature,
)
from src.services.notam_assessment import (
    NotamAssessmentConfig,
    NotamStrikeAssessmentService,
    derive_region_focus_from_assessment as derive_notam_region_focus_from_assessment,
    probability_to_signal_feature as notam_probability_to_signal_feature,
)
from src.services.opensky_assessment import (
    OpenSkyAssessmentConfig,
    OpenSkyStrikeAssessmentService,
    derive_region_focus_from_assessment,
    probability_to_signal_feature,
)
from src.services.pizza_index_pipeline import (
    build_latest_snapshot as load_latest_pizza_index_snapshot,
    refresh_snapshot as load_refreshed_pizza_index_snapshot,
)
from src.storage.signal_store import SignalStore


BASELINE_FEATURES = FeatureSet(
    flight_anomaly=0.25,
    notam_spike=0.42,
    satellite_buildup=0.37,
    news_volume=0.61,
    osint_activity=0.49,
    pizza_index=0.18,
)

DASHBOARD_SOURCE_NAMES = (
    "OpenSky Network",
    "NOTAM Feed",
    "GDELT",
    "Pizza Index Activity",
)

SIGNAL_REFRESH_SOURCE_NAMES = {"OpenSky Network", "GDELT"}
NOTAM_SIGNAL_VERSION = "notam-strike-v1"

NOTAM_STRIKE_KEYWORDS = (
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
)

NOTAM_URGENT_KEYWORDS = (
    "IMMEDIATE",
    "URGENT",
    "UNTIL FURTHER NOTICE",
    "NOW",
    "ACTIVE",
)

NOTAM_EXACT_LOCATION_CONTEXT: dict[str, tuple[str, str]] = {
    "KZLC": ("Salt Lake City ARTCC / FIR", "United States"),
    "EGTT": ("London FIR", "United Kingdom"),
    "CYOO": ("Toronto FIR", "Canada"),
    "VOBZ": ("Chennai FIR", "India"),
    "LLBG": ("Tel Aviv FIR", "Israel"),
    "RJTT": ("Tokyo FIR", "Japan"),
    "OIYY": ("Tehran FIR", "Iran"),
    "KATL": ("Atlanta ARTCC / FIR", "United States"),
    "KADW": ("Washington ARTCC / FIR", "United States"),
    "KPAM": ("Anchorage Oceanic / FIR", "United States"),
}

NOTAM_PREFIX_LOCATION_CONTEXT: tuple[tuple[str, str, str], ...] = (
    ("K", "United States domestic ARTCC / FIR system", "United States"),
    ("P", "United States Pacific ARTCC / FIR system", "United States"),
    ("C", "Canadian FIR system", "Canada"),
    ("EG", "United Kingdom FIR system", "United Kingdom"),
    ("ED", "German FIR system", "Germany"),
    ("ET", "German FIR system", "Germany"),
    ("LF", "French FIR system", "France"),
    ("LE", "Spanish FIR system", "Spain"),
    ("LI", "Italian FIR system", "Italy"),
    ("LR", "Romanian FIR system", "Romania"),
    ("LL", "Israeli FIR system", "Israel"),
    ("OI", "Iranian FIR system", "Iran"),
    ("RJ", "Japanese FIR system", "Japan"),
    ("RK", "South Korean FIR system", "South Korea"),
    ("VO", "Indian FIR system", "India"),
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


@dataclass(frozen=True)
class CollectedSourceObservation:
    source_name: str
    collected_at: datetime
    status: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class SingleSourceRefreshResult:
    feature_name: str | None
    feature_value: float | None
    observation: CollectedSourceObservation
    source: SignalSource
    region_focus: str | None = None


def _mode_from_source_status(status: str) -> str:
    return "live" if status == "active" else "fallback"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _gdelt_feature_value(
    *, assessment: object, heuristic_news_volume: float
) -> float:
    if getattr(assessment, "status", None) == "ready" and getattr(
        assessment, "probability_percent", None
    ) is not None:
        return gdelt_probability_to_signal_feature(assessment)
    return 0.0


def _gdelt_payload_for_storage(payload: dict[str, Any], fallback_reason: str | None) -> dict[str, Any]:
    stored_payload = dict(payload)
    if fallback_reason:
        stored_payload["_fallback_reason"] = fallback_reason
    else:
        stored_payload.pop("_fallback_reason", None)
    return stored_payload


def _gdelt_fallback_reason_from_payload(payload: dict[str, Any]) -> str | None:
    fallback_reason = payload.get("_fallback_reason")
    return str(fallback_reason) if isinstance(fallback_reason, str) and fallback_reason.strip() else None


def _gdelt_payload_with_assessment(
    payload: dict[str, Any], assessment: GdeltSignalAssessment | None
) -> dict[str, Any]:
    stored_payload = dict(payload)
    if assessment is None:
        stored_payload.pop("_assessment", None)
    else:
        stored_payload["_assessment"] = assessment.model_dump(mode="json")
    return stored_payload


def _gdelt_assessment_from_payload(payload: dict[str, Any]) -> GdeltSignalAssessment | None:
    raw_assessment = payload.get("_assessment")
    if not isinstance(raw_assessment, dict):
        return None
    try:
        return GdeltSignalAssessment(**raw_assessment)
    except Exception:
        return None


def _build_gdelt_manual_assessment(
    signal_article_count: int, freshness_score: float
) -> GdeltSignalAssessment:
    return GdeltSignalAssessment(
        status="disabled",
        prompt_version="gdelt-strike-v1",
        probability_percent=None,
        target_region=None,
        target_country=None,
        summary=(
            "AI assessment has not been run for the current GDELT article snapshot. "
            "Use Refresh Signal to generate it manually."
        ),
        assessed_article_count=signal_article_count,
        freshness_score=freshness_score,
    )


def _opensky_payload_with_assessment(
    payload: dict[str, Any], assessment: OpenSkyStrikeAssessment | None
) -> dict[str, Any]:
    stored_payload = dict(payload)
    if assessment is None:
        stored_payload.pop("_assessment", None)
    else:
        stored_payload["_assessment"] = assessment.model_dump(mode="json")
    return stored_payload


def _opensky_assessment_from_payload(payload: dict[str, Any]) -> OpenSkyStrikeAssessment | None:
    raw_assessment = payload.get("_assessment")
    if not isinstance(raw_assessment, dict):
        return None
    try:
        return OpenSkyStrikeAssessment(**raw_assessment)
    except Exception:
        return None


def _build_opensky_manual_assessment() -> OpenSkyStrikeAssessment:
    return OpenSkyStrikeAssessment(
        status="disabled",
        prompt_version="opensky-strike-v2",
        probability_percent=None,
        countries=[],
        explanation=(
            "AI assessment has not been run for the current OpenSky anomaly snapshot. "
            "Use Refresh Signal to generate it manually."
        ),
    )


def _notam_payload_with_assessment(
    payload: dict[str, Any], assessment: NotamSignalAssessment | None
) -> dict[str, Any]:
    stored_payload = dict(payload)
    if assessment is None:
        stored_payload.pop("_assessment", None)
    else:
        stored_payload["_assessment"] = assessment.model_dump(mode="json")
    return stored_payload


def _notam_probability_to_signal_feature(assessment: NotamSignalAssessment) -> float:
    if assessment.status != "ready" or assessment.probability_percent is None:
        return 0.0
    return round(assessment.probability_percent / 100.0, 4)


def _derive_notam_region_focus_from_assessment(
    assessment: NotamSignalAssessment, fallback: str
) -> str:
    if assessment.status != "ready":
        return fallback
    if assessment.target_country:
        return assessment.target_country
    if assessment.target_region:
        return assessment.target_region
    return fallback


def _normalize_notam_location(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(character for character in value.upper() if character.isalnum())
    return normalized or None


def _infer_notam_location_hint(location: str | None) -> tuple[str | None, str | None]:
    normalized_location = _normalize_notam_location(location)
    if normalized_location is None:
        return None, None

    for prefix, country, region in NOTAM_LOCATION_HINTS:
        if normalized_location.startswith(prefix):
            return country, region
    return None, None


def _notam_notice_haystack(notice: NotamNotice) -> str:
    return f"{notice.classification or ''} {notice.location or ''} {notice.text}".upper()


def _notam_effective_window_hours(notice: NotamNotice) -> float | None:
    start = _coerce_datetime(notice.effective_start)
    end = _coerce_datetime(notice.effective_end)
    if start is None or end is None:
        return None
    delta = end - start
    return max(delta.total_seconds() / 3600.0, 0.0)


def _notam_location_country_counts(
    notices: list[NotamNotice],
) -> tuple[dict[str, int], dict[str, int]]:
    country_counts: dict[str, int] = Counter()
    region_counts: dict[str, int] = Counter()

    for notice in notices:
        country, region = _infer_notam_location_hint(notice.location)
        if country is not None:
            country_counts[country] += 1
            if region is None:
                region = COUNTRY_REGION_HINTS.get(country)
        explicit_region = _notam_explicit_region_hint(notice)
        if explicit_region is not None:
            region_counts[explicit_region] += 1
        elif region is not None:
            region_counts[region] += 1

    return dict(country_counts), dict(region_counts)


def _notam_explicit_region_hint(notice: NotamNotice) -> str | None:
    haystack = _notam_notice_haystack(notice)
    for keyword, region in NOTAM_TEXT_REGION_HINTS:
        if keyword in haystack:
            return region
    return None


def _notam_notice_score(notice: NotamNotice, location_counts: dict[str, int]) -> float:
    haystack = _notam_notice_haystack(notice)
    score = 0.06

    if _notam_is_alert(notice):
        score += 0.18
    if _notam_is_restricted(notice):
        score += 0.10
    if any(keyword in haystack for keyword in NOTAM_STRIKE_KEYWORDS):
        score += 0.16
    if any(keyword in haystack for keyword in NOTAM_URGENT_KEYWORDS):
        score += 0.05

    window_hours = _notam_effective_window_hours(notice)
    if window_hours is not None:
        if window_hours <= 6:
            score += 0.18
        elif window_hours <= 24:
            score += 0.14
        elif window_hours <= 72:
            score += 0.08

    location = notice.location
    if location is not None:
        repeated_location_count = location_counts.get(location.upper(), 0)
        if repeated_location_count > 1:
            score += min((repeated_location_count - 1) * 0.05, 0.15)

    if _infer_notam_location_hint(notice.location)[0] is not None:
        score += 0.04

    return min(score, 1.0)


def _build_notam_signal_assessment(notices: list[NotamNotice]) -> NotamSignalAssessment:
    if not notices:
        return NotamSignalAssessment(
            status="disabled",
            prompt_version=NOTAM_SIGNAL_VERSION,
            probability_percent=None,
            target_region=None,
            target_country=None,
            summary=(
                "No parseable NOTAM notices were available in the stored snapshot. "
                "Refresh the source first, then run Refresh Signal."
            ),
            assessed_notice_count=0,
            freshness_score=0.0,
        )

    location_counts = Counter(
        notice.location.upper()
        for notice in notices
        if isinstance(notice.location, str) and notice.location.strip()
    )
    country_counts, region_counts = _notam_location_country_counts(notices)
    notice_scores = [_notam_notice_score(notice, dict(location_counts)) for notice in notices]
    ranked_scores = sorted(notice_scores, reverse=True)
    top_scores = ranked_scores[:3]
    top_average = sum(top_scores) / len(top_scores) if top_scores else 0.0

    alert_count = sum(1 for notice in notices if _notam_is_alert(notice))
    restricted_count = sum(1 for notice in notices if _notam_is_restricted(notice))
    short_window_count = sum(
        1
        for notice in notices
        if (window_hours := _notam_effective_window_hours(notice)) is not None and window_hours <= 24
    )
    active_window_count = sum(
        1
        for notice in notices
        if (window_hours := _notam_effective_window_hours(notice)) is not None and window_hours <= 72
    )
    location_concentration = 0.0
    if location_counts:
        location_concentration = min((max(location_counts.values()) - 1) * 0.12, 0.24)

    country_name = None
    country_weight = 0
    if country_counts:
        country_name = max(country_counts.items(), key=lambda item: (item[1], item[0]))[0]
        country_weight = country_counts[country_name]

    region_name = None
    if region_counts:
        region_name = max(region_counts.items(), key=lambda item: (item[1], item[0]))[0]

    country_confidence = 0.0
    if country_name is not None:
        country_confidence = min(country_weight / max(len(notices), 1), 1.0)
        if country_confidence < 0.34 and region_name is None:
            country_name = None

    target_region = region_name
    target_country = country_name
    if target_country is not None:
        target_region = COUNTRY_REGION_HINTS.get(target_country, target_region)

    explicit_region_bonus = 0.10 if target_region is not None else 0.0
    country_bonus = 0.10 if target_country is not None else 0.0
    urgency_bonus = 0.0
    if active_window_count:
        urgency_bonus += min(active_window_count / len(notices), 1.0) * 0.08
    if short_window_count:
        urgency_bonus += min(short_window_count / len(notices), 1.0) * 0.08

    probability = (
        0.42 * top_average
        + 0.18 * (alert_count / len(notices))
        + 0.10 * (restricted_count / len(notices))
        + 0.12 * location_concentration
        + explicit_region_bonus
        + country_bonus
        + urgency_bonus
    )
    probability = min(max(probability, 0.0), 0.98)
    probability_percent = int(round(probability * 100))

    strongest_location = None
    if location_counts:
        strongest_location = max(location_counts.items(), key=lambda item: (item[1], item[0]))[0]
    strongest_score = max(notice_scores) if notice_scores else 0.0
    region_fragment = (
        f" clustered around {target_country}" if target_country is not None else (
            f" clustered around {target_region}" if target_region is not None else ""
        )
    )
    if strongest_location is not None:
        location_fragment = f" Most concentrated location: {strongest_location}."
    else:
        location_fragment = ""

    summary = (
        f"Heuristic NOTAM refresh estimates a {probability_percent}% strike-risk probability from "
        f"{len(notices)} notices. {alert_count} notices are alert-level and {restricted_count} are restricted."
        f"{region_fragment}{location_fragment} Strongest notice score: {round(strongest_score, 2)}."
    )

    freshness_score = 0.0
    if notices:
        freshness_score = round(
            min(
                1.0,
                (
                    min(active_window_count / len(notices), 1.0) * 0.6
                    + min(short_window_count / len(notices), 1.0) * 0.4
                ),
            ),
            4,
        )

    return NotamSignalAssessment(
        status="ready",
        prompt_version=NOTAM_SIGNAL_VERSION,
        probability_percent=probability_percent,
        target_region=target_region,
        target_country=target_country,
        summary=summary,
        assessed_notice_count=len(notices),
        freshness_score=freshness_score,
    )


def _build_pizza_index_source(snapshot: PizzaIndexSnapshotResponse) -> SignalSource:
    has_any_coverage = (
        snapshot.quality_summary.full_count + snapshot.quality_summary.partial_count > 0
    )
    has_coverage_gap = (
        snapshot.quality_summary.partial_count > 0
        or snapshot.quality_summary.unavailable_count > 0
    )
    status = "planned"
    mode = "static_baseline"
    if has_any_coverage:
        status = "degraded" if has_coverage_gap else "active"
        mode = "fallback" if has_coverage_gap else "live"
    return SignalSource(
        name="Pizza Index Activity",
        status=status,
        mode=mode,
        last_checked_at=snapshot.generated_at,
    )


def _pizza_index_observation(snapshot: PizzaIndexSnapshotResponse) -> CollectedSourceObservation:
    source = _build_pizza_index_source(snapshot)
    return CollectedSourceObservation(
        source_name=source.name,
        collected_at=snapshot.generated_at,
        status=source.status,
        payload=snapshot.model_dump(mode="json"),
    )


def _snapshot_matches_current_contract(snapshot: LatestSignalsResponse) -> bool:
    source_names = {source.name for source in snapshot.sources}
    return source_names == set(DASHBOARD_SOURCE_NAMES)


def _blank_snapshot() -> LatestSignalsResponse:
    return LatestSignalsResponse(
        generated_at=_utc_now(),
        region_focus="none",
        features=BASELINE_FEATURES,
        sources=[],
    )


def _replace_source(
    sources: list[SignalSource], updated_source: SignalSource
) -> list[SignalSource]:
    replaced = False
    updated_sources: list[SignalSource] = []
    for source in sources:
        if source.name == updated_source.name:
            updated_sources.append(updated_source)
            replaced = True
        else:
            updated_sources.append(source)
    if not replaced:
        updated_sources.append(updated_source)
    return updated_sources


def _save_snapshot_projection(
    store: SignalStore,
    latest_snapshot: LatestSignalsResponse,
    *,
    source: SignalSource | None = None,
    feature_updates: dict[str, float] | None = None,
    region_focus: str | None = None,
    generated_at: datetime | None = None,
) -> LatestSignalsResponse:
    updated_sources = latest_snapshot.sources
    if source is not None:
        updated_sources = _replace_source(latest_snapshot.sources, source)

    candidates = [latest_snapshot.generated_at]
    if generated_at is not None:
        candidates.append(generated_at)
    if source is not None and source.last_checked_at is not None:
        candidates.append(source.last_checked_at)

    snapshot = LatestSignalsResponse(
        generated_at=max(candidates),
        region_focus=region_focus or latest_snapshot.region_focus,
        features=latest_snapshot.features.model_copy(update=feature_updates or {}),
        sources=updated_sources,
    )
    return store.save_signal_snapshot(snapshot)


def build_snapshot_from_sources() -> LatestSignalsResponse:
    return refresh_latest_snapshot()


def _refreshable_source_names() -> set[str]:
    return set(DASHBOARD_SOURCE_NAMES)


def _collect_single_source(source_name: str) -> SingleSourceRefreshResult:
    settings = get_settings()

    if source_name == "OpenSky Network":
        observation = OpenSkyCollector().fetch_observation()
        feature_name = None
        feature_value = None
        payload = _opensky_payload_with_assessment(observation.raw_payload, None)
    elif source_name == "NOTAM Feed":
        observation = NotamCollector(
            source_url=settings.notam_source_url,
            auth_url=settings.notam_auth_url,
            api_base_url=settings.notam_api_base_url,
            client_id=settings.notam_client_id,
            client_secret=settings.notam_client_secret,
            classification=settings.notam_classification,
            accountability=settings.notam_accountability,
            location=settings.notam_location,
            response_format=settings.notam_response_format,
            detail_fetch_enabled=settings.notam_detail_fetch_enabled,
            max_items=settings.notam_max_items,
            timeout_seconds=settings.notam_timeout_seconds,
        ).fetch_observation()
        feature_name = "notam_spike"
        feature_value = observation.notam_spike
        payload = observation.raw_payload
    elif source_name == "GDELT":
        observation = GdeltCollector(
            source_url=settings.gdelt_source_url,
            timeout_seconds=settings.gdelt_timeout_seconds,
        ).fetch_observation()
        feature_name = None
        feature_value = None
        payload = _gdelt_payload_with_assessment(
            _gdelt_payload_for_storage(
                observation.raw_payload,
                observation.fallback_reason,
            ),
            None,
        )
    elif source_name == "Pizza Index Activity":
        pizza_snapshot = load_refreshed_pizza_index_snapshot()
        source = _build_pizza_index_source(pizza_snapshot)
        pizza_observation = _pizza_index_observation(pizza_snapshot)
        return SingleSourceRefreshResult(
            feature_name="pizza_index",
            feature_value=pizza_snapshot.pizza_index,
            observation=pizza_observation,
            source=source,
        )
    else:
        raise ValueError(f"Signal source does not support individual refresh: {source_name}")

    source = SignalSource(
        name=source_name,
        status=observation.status,
        mode=_mode_from_source_status(observation.status),
        last_checked_at=observation.collected_at,
    )
    return SingleSourceRefreshResult(
        feature_name=feature_name,
        feature_value=feature_value,
        observation=CollectedSourceObservation(
            source_name=source_name,
            collected_at=observation.collected_at,
            status=observation.status,
            payload=payload,
        ),
        source=source,
    )


def _persist_source_only_refresh(
    store: SignalStore,
    latest_snapshot: LatestSignalsResponse,
    source_name: str,
) -> SignalSourceRefreshResponse:
    refresh_result = _collect_single_source(source_name)
    store.save_source_observation(
        source_name=refresh_result.observation.source_name,
        collected_at=refresh_result.observation.collected_at,
        status=refresh_result.observation.status,
        payload=refresh_result.observation.payload,
    )

    feature_updates: dict[str, float] = {}
    if (
        refresh_result.feature_name is not None
        and refresh_result.feature_value is not None
        and source_name not in SIGNAL_REFRESH_SOURCE_NAMES
    ):
        feature_updates[refresh_result.feature_name] = refresh_result.feature_value

    persisted_snapshot = _save_snapshot_projection(
        store,
        latest_snapshot,
        source=refresh_result.source,
        feature_updates=feature_updates,
        generated_at=refresh_result.observation.collected_at,
    )
    refreshed_source = next(
        source for source in persisted_snapshot.sources if source.name == source_name
    )
    return SignalSourceRefreshResponse(
        source=refreshed_source,
        snapshot=persisted_snapshot,
    )


def refresh_source_detail(source_name: str) -> SignalSourceRefreshResponse:
    if source_name not in _refreshable_source_names():
        raise ValueError(f"Signal source does not support individual refresh: {source_name}")

    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = store.get_latest_signal_snapshot()
    if latest_snapshot is None or not _snapshot_matches_current_contract(latest_snapshot):
        latest_snapshot = refresh_latest_snapshot()
    return _persist_source_only_refresh(store, latest_snapshot, source_name)


def _ensure_latest_source_payload(
    store: SignalStore,
    latest_snapshot: LatestSignalsResponse,
    source_name: str,
) -> tuple[LatestSignalsResponse, dict[str, Any]]:
    latest = store.get_latest_source_observation(source_name)
    if latest is not None:
        return latest_snapshot, latest

    source_refresh = _persist_source_only_refresh(store, latest_snapshot, source_name)
    latest = store.get_latest_source_observation(source_name)
    if latest is None:
        raise RuntimeError(f"No stored source observation is available for {source_name}")
    return source_refresh.snapshot, latest


def get_or_create_latest_snapshot() -> LatestSignalsResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    snapshot = store.get_latest_signal_snapshot()
    if snapshot is not None and _snapshot_matches_current_contract(snapshot):
        return snapshot
    return refresh_latest_snapshot()


def refresh_latest_snapshot() -> LatestSignalsResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = store.get_latest_signal_snapshot()
    if latest_snapshot is None or not _snapshot_matches_current_contract(latest_snapshot):
        latest_snapshot = _blank_snapshot()

    for source_name in DASHBOARD_SOURCE_NAMES:
        source_refresh = _persist_source_only_refresh(store, latest_snapshot, source_name)
        latest_snapshot = source_refresh.snapshot
        if source_name == "OpenSky Network":
            latest_snapshot = _refresh_opensky_signal_from_snapshot(store, latest_snapshot).snapshot
        elif source_name == "GDELT":
            latest_snapshot = _refresh_gdelt_signal_from_snapshot(store, latest_snapshot).snapshot

    return latest_snapshot


def refresh_signal_source(source_name: str) -> SignalSourceRefreshResponse:
    if source_name not in _refreshable_source_names():
        raise ValueError(f"Signal source does not support individual refresh: {source_name}")

    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = store.get_latest_signal_snapshot()
    if latest_snapshot is None or not _snapshot_matches_current_contract(latest_snapshot):
        latest_snapshot = refresh_latest_snapshot()

    source_refresh = _persist_source_only_refresh(store, latest_snapshot, source_name)
    if source_name == "OpenSky Network":
        signal_refresh = _refresh_opensky_signal_from_snapshot(store, source_refresh.snapshot)
        return SignalSourceRefreshResponse(
            source=signal_refresh.source,
            snapshot=signal_refresh.snapshot,
        )
    if source_name == "GDELT":
        signal_refresh = _refresh_gdelt_signal_from_snapshot(store, source_refresh.snapshot)
        return SignalSourceRefreshResponse(
            source=signal_refresh.source,
            snapshot=signal_refresh.snapshot,
        )
    return source_refresh


def get_latest_opensky_anomalies() -> OpenSkyAnomaliesResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest = store.get_latest_source_observation("OpenSky Network")

    if latest is None:
        latest_snapshot = store.get_latest_signal_snapshot() or _blank_snapshot()
        _, latest = _ensure_latest_source_payload(store, latest_snapshot, "OpenSky Network")

    collected_at = datetime.fromisoformat(latest["collected_at"])
    status = latest["status"]
    states = parse_states(latest["payload"])
    cached_assessment = _opensky_assessment_from_payload(latest["payload"])

    anomaly_assessments = assess_opensky_anomalies(states)
    anomalies: list[OpenSkyAnomaly] = []
    for assessment in anomaly_assessments:
        state = assessment.state
        anomalies.append(
            OpenSkyAnomaly(
                icao24=state.icao24,
                callsign=state.callsign,
                origin_country=state.origin_country,
                latitude=state.latitude,
                longitude=state.longitude,
                baro_altitude=state.baro_altitude,
                velocity=state.velocity,
                geo_altitude=state.geo_altitude,
                reasons=list(assessment.reasons),
            )
        )

    ai_assessment = cached_assessment or _build_opensky_manual_assessment()

    return OpenSkyAnomaliesResponse(
        generated_at=collected_at,
        status=status,
        flight_anomaly=probability_to_signal_feature(ai_assessment),
        anomalies=anomalies,
        assessment=ai_assessment,
    )


def _refresh_opensky_signal_from_snapshot(
    store: SignalStore, latest_snapshot: LatestSignalsResponse
) -> OpenSkySignalRefreshResponse:
    latest_snapshot, latest = _ensure_latest_source_payload(
        store,
        latest_snapshot,
        "OpenSky Network",
    )

    collected_at = datetime.fromisoformat(latest["collected_at"])
    status = latest["status"]
    source_payload = dict(latest["payload"])
    states = parse_states(source_payload)
    anomaly_assessments = assess_opensky_anomalies(states)

    settings = get_settings()
    assessment = OpenSkyStrikeAssessmentService(
        OpenSkyAssessmentConfig(
            api_url=settings.opensky_ai_api_url,
            api_key=settings.opensky_ai_api_key,
            model=settings.opensky_ai_model,
            timeout_seconds=settings.opensky_ai_timeout_seconds,
        )
    ).assess_anomalies(anomaly_assessments)

    store.save_source_observation(
        source_name="OpenSky Network",
        collected_at=collected_at,
        status=status,
        payload=_opensky_payload_with_assessment(source_payload, assessment),
    )

    refreshed_source = SignalSource(
        name="OpenSky Network",
        status=status,
        mode=_mode_from_source_status(status),
        last_checked_at=collected_at,
    )
    persisted_snapshot = _save_snapshot_projection(
        store,
        latest_snapshot,
        source=refreshed_source,
        feature_updates={
            "flight_anomaly": probability_to_signal_feature(assessment)
        },
        region_focus=derive_region_focus_from_assessment(
            assessment,
            fallback=latest_snapshot.region_focus,
        ),
        generated_at=_utc_now(),
    )
    refreshed_source = next(
        source for source in persisted_snapshot.sources if source.name == "OpenSky Network"
    )
    return OpenSkySignalRefreshResponse(
        source=refreshed_source,
        snapshot=persisted_snapshot,
        assessment=assessment,
    )


def refresh_opensky_signal() -> OpenSkySignalRefreshResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = store.get_latest_signal_snapshot()
    if latest_snapshot is None or not _snapshot_matches_current_contract(latest_snapshot):
        latest_snapshot = refresh_latest_snapshot()
    return _refresh_opensky_signal_from_snapshot(store, latest_snapshot)


def _refresh_gdelt_signal_from_snapshot(
    store: SignalStore, latest_snapshot: LatestSignalsResponse
) -> GdeltSignalRefreshResponse:
    latest_snapshot, latest = _ensure_latest_source_payload(store, latest_snapshot, "GDELT")

    collected_at = datetime.fromisoformat(latest["collected_at"])
    status = latest["status"]
    source_payload = dict(latest["payload"])
    articles = parse_articles(source_payload)

    settings = get_settings()
    assessment = GdeltStrikeAssessmentService(
        GdeltAssessmentConfig(
            api_url=settings.gdelt_ai_api_url,
            api_key=settings.gdelt_ai_api_key,
            model=settings.gdelt_ai_model,
            timeout_seconds=settings.gdelt_ai_timeout_seconds,
        )
    ).assess_articles(articles)

    store.save_source_observation(
        source_name="GDELT",
        collected_at=collected_at,
        status=status,
        payload=_gdelt_payload_with_assessment(source_payload, assessment),
    )
    refreshed_source = SignalSource(
        name="GDELT",
        status=status,
        mode=_mode_from_source_status(status),
        last_checked_at=collected_at,
    )
    persisted_snapshot = _save_snapshot_projection(
        store,
        latest_snapshot,
        source=refreshed_source,
        feature_updates={
            "news_volume": _gdelt_feature_value(
                assessment=assessment,
                heuristic_news_volume=compute_news_volume(articles),
            )
        },
        region_focus=derive_gdelt_region_focus_from_assessment(
            assessment,
            fallback=latest_snapshot.region_focus,
        ),
        generated_at=_utc_now(),
    )
    refreshed_source = next(
        source for source in persisted_snapshot.sources if source.name == "GDELT"
    )
    return GdeltSignalRefreshResponse(
        source=refreshed_source,
        snapshot=persisted_snapshot,
        assessment=assessment,
    )


def refresh_gdelt_signal() -> GdeltSignalRefreshResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = store.get_latest_signal_snapshot()
    if latest_snapshot is None or not _snapshot_matches_current_contract(latest_snapshot):
        latest_snapshot = refresh_latest_snapshot()
    return _refresh_gdelt_signal_from_snapshot(store, latest_snapshot)


def _refresh_notam_signal_from_snapshot(
    store: SignalStore, latest_snapshot: LatestSignalsResponse
) -> NotamSignalRefreshResponse:
    latest_snapshot, latest = _ensure_latest_source_payload(store, latest_snapshot, "NOTAM Feed")

    collected_at = datetime.fromisoformat(latest["collected_at"])
    status = latest["status"]
    source_payload = dict(latest["payload"])
    notices = parse_notices(source_payload)
    settings = get_settings()
    assessment = NotamStrikeAssessmentService(
        NotamAssessmentConfig(
            api_url=settings.notam_ai_api_url,
            api_key=settings.notam_ai_api_key,
            model=settings.notam_ai_model,
            timeout_seconds=settings.notam_ai_timeout_seconds,
        )
    ).assess_notices(notices)

    store.save_source_observation(
        source_name="NOTAM Feed",
        collected_at=collected_at,
        status=status,
        payload=_notam_payload_with_assessment(source_payload, assessment),
    )
    refreshed_source = SignalSource(
        name="NOTAM Feed",
        status=status,
        mode=_mode_from_source_status(status),
        last_checked_at=collected_at,
    )
    persisted_snapshot = _save_snapshot_projection(
        store,
        latest_snapshot,
        source=refreshed_source,
        feature_updates={
            "notam_spike": notam_probability_to_signal_feature(assessment),
        },
        region_focus=derive_notam_region_focus_from_assessment(
            assessment,
            fallback=latest_snapshot.region_focus,
        ),
        generated_at=_utc_now(),
    )
    refreshed_source = next(
        source for source in persisted_snapshot.sources if source.name == "NOTAM Feed"
    )
    return NotamSignalRefreshResponse(
        source=refreshed_source,
        snapshot=persisted_snapshot,
        assessment=assessment,
    )


def refresh_notam_signal() -> NotamSignalRefreshResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = store.get_latest_signal_snapshot()
    if latest_snapshot is None or not _snapshot_matches_current_contract(latest_snapshot):
        latest_snapshot = refresh_latest_snapshot()
    return _refresh_notam_signal_from_snapshot(store, latest_snapshot)


def _rank_counts(items: list[str], limit: int = 5) -> list[GdeltCountBreakdown]:
    counts = Counter(items)
    return [
        GdeltCountBreakdown(label=label, count=count)
        for label, count in counts.most_common(limit)
    ]


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


def _find_latest_datetime(payload: Any, *keys: str) -> datetime | None:
    found: list[datetime] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in keys:
                    dt_value = _coerce_datetime(value)
                    if dt_value is not None:
                        found.append(dt_value)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
    return max(found) if found else None


def _find_effective_window(notices: list[NotamNotice]) -> tuple[datetime | None, datetime | None]:
    starts = [_coerce_datetime(notice.effective_start) for notice in notices]
    ends = [_coerce_datetime(notice.effective_end) for notice in notices]
    start_values = [value for value in starts if value is not None]
    end_values = [value for value in ends if value is not None]
    return (
        min(start_values) if start_values else None,
        max(end_values) if end_values else None,
    )


def _notam_is_alert(notice: NotamNotice) -> bool:
    haystack = f"{notice.classification or ''} {notice.text}".upper()
    return any(keyword in haystack for keyword in NOTAM_ALERT_KEYWORDS)


def _notam_is_restricted(notice: NotamNotice) -> bool:
    haystack = f"{notice.classification or ''} {notice.text}".upper()
    return any(keyword in haystack for keyword in ("RESTRICT", "TFR", "AIRSPACE RESTRICTION"))


def _notam_is_military_relevant(notice: NotamNotice) -> bool:
    haystack = f"{notice.classification or ''} {notice.text}".upper()
    return (
        _notam_is_alert(notice)
        or _notam_is_restricted(notice)
        or "MILITARY" in haystack
    )


def _notam_notice_priority(notice: NotamNotice) -> tuple[int, int, datetime]:
    start = _coerce_datetime(notice.effective_start)
    end = _coerce_datetime(notice.effective_end)
    effective_dt = end or start or datetime.min.replace(tzinfo=UTC)
    return (
        1 if _notam_is_alert(notice) else 0,
        1 if _notam_is_restricted(notice) else 0,
        effective_dt,
    )


def _normalize_notam_location_code(location: str | None) -> str | None:
    if not isinstance(location, str):
        return None
    normalized = location.strip().upper()
    return normalized or None


def _notam_location_context(location: str | None) -> tuple[str | None, str | None, str | None]:
    return resolve_notam_location_context(location)


def _notam_notice_summary(notice: NotamNotice) -> NotamNoticeSummary:
    icao_code, fir_name, country_name = _notam_location_context(notice.location)
    return NotamNoticeSummary(
        notice_id=notice.notice_id,
        location=notice.location,
        icao_code=icao_code,
        fir_name=fir_name,
        country_name=country_name,
        classification=notice.classification,
        text=notice.text,
        effective_start=_coerce_datetime(notice.effective_start),
        effective_end=_coerce_datetime(notice.effective_end),
        is_alert=_notam_is_alert(notice),
        is_restricted=_notam_is_restricted(notice),
    )


def _notam_count_breakdown(values: list[str]) -> list[NotamCountBreakdown]:
    return [
        NotamCountBreakdown(label=label, count=count)
        for label, count in Counter(values).most_common()
    ]


def _notam_location_breakdown(values: list[str], limit: int = 6) -> list[NotamCountBreakdown]:
    breakdown: list[NotamCountBreakdown] = []
    for label, count in Counter(values).most_common(limit):
        _, fir_name, country_name = _notam_location_context(label)
        breakdown.append(
            NotamCountBreakdown(
                label=label,
                count=count,
                fir_name=fir_name,
                country_name=country_name,
            )
        )
    return breakdown


def _notam_fallback_reason_from_payload(payload: dict[str, Any]) -> str | None:
    fallback_reason = payload.get("_fallback_reason")
    if isinstance(fallback_reason, str) and fallback_reason.strip():
        return fallback_reason.strip()
    return None


def get_latest_notam_detail() -> NotamDetailResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest = store.get_latest_source_observation("NOTAM Feed")

    if latest is None:
        latest_snapshot = store.get_latest_signal_snapshot() or _blank_snapshot()
        _, latest = _ensure_latest_source_payload(store, latest_snapshot, "NOTAM Feed")

    collected_at = datetime.fromisoformat(latest["collected_at"])
    status = latest["status"]
    payload = latest["payload"]
    notices = parse_notices(payload)
    fallback_reason = _notam_fallback_reason_from_payload(payload)

    sorted_notices = sorted(notices, key=_notam_notice_priority, reverse=True)
    representative_notices = [
        _notam_notice_summary(notice)
        for notice in sorted_notices[:5]
    ]
    military_relevant_notices = [notice for notice in notices if _notam_is_military_relevant(notice)]
    alert_notice_count = sum(1 for notice in notices if _notam_is_alert(notice))
    restricted_notice_count = sum(1 for notice in notices if _notam_is_restricted(notice))
    classification_breakdown = _notam_count_breakdown(
        [(notice.classification.strip() if isinstance(notice.classification, str) and notice.classification.strip() else "Unspecified") for notice in notices]
    )
    location_breakdown = _notam_location_breakdown(
        [
            (notice.location.strip() if isinstance(notice.location, str) and notice.location.strip() else "Unspecified")
            for notice in military_relevant_notices
        ]
    )
    latest_updated_at = _find_latest_datetime(
        payload,
        "lastUpdated",
        "lastUpdatedDate",
        "lastUpdate",
        "updateTs",
    )
    effective_window_start, effective_window_end = _find_effective_window(notices)

    if notices:
        location_count = len({notice.location for notice in notices if notice.location})
        summary = (
            f"Latest stored NOTAM observation contains {len(notices)} notices across "
            f"{location_count} locations. "
            f"{alert_notice_count} are alert-level and {restricted_notice_count} are restricted."
        )
    else:
        summary = "Latest stored NOTAM observation contains no parseable notices."

    if fallback_reason:
        summary = f"{summary} Collector fallback: {fallback_reason}."

    return NotamDetailResponse(
        generated_at=collected_at,
        status=status,
        summary=summary,
        notice_count=len(notices),
        alert_notice_count=alert_notice_count,
        restricted_notice_count=restricted_notice_count,
        notam_spike=compute_notam_spike(notices),
        latest_updated_at=latest_updated_at,
        effective_window_start=effective_window_start,
        effective_window_end=effective_window_end,
        classification_breakdown=classification_breakdown,
        location_breakdown=location_breakdown,
        representative_notices=representative_notices,
        collector_fallback_reason=fallback_reason,
    )


def get_latest_gdelt_detail() -> GdeltDetailResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest = store.get_latest_source_observation("GDELT")

    if latest is None:
        latest_snapshot = store.get_latest_signal_snapshot() or _blank_snapshot()
        _, latest = _ensure_latest_source_payload(store, latest_snapshot, "GDELT")

    collected_at = datetime.fromisoformat(latest["collected_at"])
    status = latest["status"]
    articles = parse_articles(latest["payload"])
    news_volume = compute_news_volume(articles)
    fallback_reason = _gdelt_fallback_reason_from_payload(latest["payload"])

    recent_articles = filter_recent_articles(articles)
    alert_articles = [article for article in recent_articles if is_alert_article(article)]
    signal_articles = build_signal_article_set(recent_articles)
    if signal_articles:
        freshness_score = round(
            sum(compute_article_freshness_score(article) for article in signal_articles)
            / len(signal_articles),
            4,
        )
    else:
        freshness_score = 0.0
    assessment = _gdelt_assessment_from_payload(latest["payload"])
    if assessment is None:
        assessment = _build_gdelt_manual_assessment(
            signal_article_count=len(signal_articles),
            freshness_score=freshness_score,
        )
    top_regions = _rank_counts(
        [region for article in recent_articles for region in extract_article_regions(article)]
    )
    top_themes = _rank_counts(
        [theme for article in recent_articles for theme in extract_article_themes(article)]
    )
    top_sources = _rank_counts([article_source_label(article) for article in recent_articles])
    headlines = [
        GdeltHeadline(
            article_id=article.article_id,
            title=article.title,
            source=article.source,
            source_label=article_source_label(article),
            published_at=article.published_at,
            url=article.url,
            is_alert=is_alert_article(article),
            is_us_nato_actor=is_us_nato_actor_article(article),
            is_action_indicative=is_action_indicative_article(article),
            freshness_score=compute_article_freshness_score(article),
            themes=extract_article_themes(article),
            regions=extract_article_regions(article),
        )
        for article in recent_articles[:8]
    ]
    alert_share = (
        round((len(alert_articles) / len(recent_articles)), 4) if recent_articles else 0.0
    )

    return GdeltDetailResponse(
        generated_at=collected_at,
        status=status,
        news_volume=compute_news_volume(recent_articles) if recent_articles else news_volume,
        article_count=len(recent_articles),
        alert_article_count=len(alert_articles),
        signal_article_count=len(signal_articles),
        freshness_score=assessment.freshness_score,
        alert_share=alert_share,
        volume_delta=None,
        top_regions=top_regions,
        top_themes=top_themes,
        top_sources=top_sources,
        headlines=headlines,
        assessment=assessment,
        provenance=GdeltProvenance(
            source_url_configured=bool(settings.gdelt_source_url),
            keyword_watchlist=list(sorted(GDELT_ALERT_KEYWORDS)),
            theme_derivation="Keyword-derived from article title and body text.",
            region_derivation="Keyword-derived from article title and body text.",
            comparison_basis="Signal refresh uses freshness-weighted, US/NATO-specific article selection with AI assessment; prior-window comparison is still unavailable.",
            collector_fallback_reason=fallback_reason,
        ),
    )
