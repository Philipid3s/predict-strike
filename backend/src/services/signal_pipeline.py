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
from src.collectors.notam import NotamCollector
from src.collectors.opensky import (
    OpenSkyCollector,
    assess_opensky_anomalies,
    dominant_suspicious_region_name,
    parse_states,
)
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
            source_url=settings.notam_source_url
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


def _rank_counts(items: list[str], limit: int = 5) -> list[GdeltCountBreakdown]:
    counts = Counter(items)
    return [
        GdeltCountBreakdown(label=label, count=count)
        for label, count in counts.most_common(limit)
    ]


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
