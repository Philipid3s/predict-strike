from dataclasses import dataclass
from datetime import datetime
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
    compute_flight_anomaly,
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


@dataclass(frozen=True)
class SingleSourceRefreshResult:
    feature_name: str | None
    feature_value: float | None
    observation: CollectedSourceObservation
    source: SignalSource
    region_focus: str | None = None


def _mode_from_source_status(status: str) -> str:
    return "live" if status == "active" else "fallback"


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
        source_url=settings.gdelt_source_url,
        timeout_seconds=settings.gdelt_timeout_seconds,
    ).fetch_observation()
    gdelt_assessment = GdeltStrikeAssessmentService(
        GdeltAssessmentConfig(
            api_url=settings.gdelt_ai_api_url,
            api_key=settings.gdelt_ai_api_key,
            model=settings.gdelt_ai_model,
            timeout_seconds=settings.gdelt_ai_timeout_seconds,
        )
    ).assess_articles(gdelt_observation.articles)
    generated_at = max(
        opensky_observation.collected_at,
        notam_observation.collected_at,
        gdelt_observation.collected_at,
    )
    return CollectedSignalInputs(
        generated_at=generated_at,
        region_focus=dominant_suspicious_region_name(opensky_observation.states) or "none",
        flight_anomaly=BASELINE_FEATURES.flight_anomaly,
        notam_spike=notam_observation.notam_spike,
        news_volume=_gdelt_feature_value(
            assessment=gdelt_assessment,
            heuristic_news_volume=gdelt_observation.news_volume,
        ),
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
                payload=_gdelt_payload_for_storage(
                    gdelt_observation.raw_payload,
                    gdelt_observation.fallback_reason,
                ),
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


def _refreshable_source_names() -> set[str]:
    return {"OpenSky Network", "NOTAM Feed", "GDELT"}


def _collect_single_source(source_name: str) -> SingleSourceRefreshResult:
    settings = get_settings()

    if source_name == "OpenSky Network":
        observation = OpenSkyCollector().fetch_observation()
        feature_name = None
        feature_value = None
        region_focus = None
    elif source_name == "NOTAM Feed":
        observation = NotamCollector(
            source_url=settings.notam_source_url
        ).fetch_observation()
        feature_name = "notam_spike"
        feature_value = observation.notam_spike
        region_focus = None
    elif source_name == "GDELT":
        observation = GdeltCollector(
            source_url=settings.gdelt_source_url,
            timeout_seconds=settings.gdelt_timeout_seconds,
        ).fetch_observation()
        feature_name = None
        feature_value = None
        region_focus = None
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
            payload=(
                _gdelt_payload_for_storage(
                    observation.raw_payload,
                    observation.fallback_reason,
                )
                if source_name == "GDELT"
                else observation.raw_payload
            ),
        ),
        source=source,
        region_focus=region_focus,
    )


def refresh_signal_source(source_name: str) -> SignalSourceRefreshResponse:
    if source_name not in _refreshable_source_names():
        raise ValueError(f"Signal source does not support individual refresh: {source_name}")

    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = get_or_create_latest_snapshot()
    refresh_result = _collect_single_source(source_name)

    store.save_source_observation(
        source_name=refresh_result.observation.source_name,
        collected_at=refresh_result.observation.collected_at,
        status=refresh_result.observation.status,
        payload=(
            _gdelt_payload_with_assessment(refresh_result.observation.payload, None)
            if refresh_result.observation.source_name == "GDELT"
            else refresh_result.observation.payload
        ),
    )

    updated_sources = [
        refresh_result.source if source.name == source_name else source
        for source in latest_snapshot.sources
    ]
    updated_snapshot = LatestSignalsResponse(
        generated_at=max(
            [
                latest_snapshot.generated_at,
                refresh_result.observation.collected_at,
                *[
                    source.last_checked_at
                    for source in updated_sources
                    if source.last_checked_at is not None
                ],
            ]
        ),
        region_focus=refresh_result.region_focus or latest_snapshot.region_focus,
        features=latest_snapshot.features.model_copy(
            update=(
                {refresh_result.feature_name: refresh_result.feature_value}
                if refresh_result.feature_name and refresh_result.feature_value is not None
                else {}
            )
        ),
        sources=updated_sources,
    )
    persisted_snapshot = store.save_signal_snapshot(updated_snapshot)
    refreshed_source = next(
        source for source in persisted_snapshot.sources if source.name == source_name
    )
    return SignalSourceRefreshResponse(
        source=refreshed_source,
        snapshot=persisted_snapshot,
    )


def get_latest_opensky_anomalies() -> OpenSkyAnomaliesResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest = store.get_latest_source_observation("OpenSky Network")

    if latest is None:
        observation = OpenSkyCollector().fetch_observation()
        store.save_source_observation(
            source_name="OpenSky Network",
            collected_at=observation.collected_at,
            status=observation.status,
            payload=_opensky_payload_with_assessment(observation.raw_payload, None),
        )
        collected_at = observation.collected_at
        status = observation.status
        states = observation.states
        cached_assessment = None
    else:
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


def refresh_opensky_signal() -> OpenSkySignalRefreshResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = get_or_create_latest_snapshot()
    refresh_result = _collect_single_source("OpenSky Network")
    states = parse_states(refresh_result.observation.payload)
    anomaly_assessments = assess_opensky_anomalies(states)
    assessment = OpenSkyStrikeAssessmentService(
        OpenSkyAssessmentConfig(
            api_url=settings.opensky_ai_api_url,
            api_key=settings.opensky_ai_api_key,
            model=settings.opensky_ai_model,
            timeout_seconds=settings.opensky_ai_timeout_seconds,
        )
    ).assess_anomalies(anomaly_assessments)

    store.save_source_observation(
        source_name=refresh_result.observation.source_name,
        collected_at=refresh_result.observation.collected_at,
        status=refresh_result.observation.status,
        payload=_opensky_payload_with_assessment(
            refresh_result.observation.payload,
            assessment,
        ),
    )

    refreshed_source = SignalSource(
        name="OpenSky Network",
        status=refresh_result.observation.status,
        mode=_mode_from_source_status(refresh_result.observation.status),
        last_checked_at=refresh_result.observation.collected_at,
    )
    updated_sources = [
        refreshed_source if source.name == "OpenSky Network" else source
        for source in latest_snapshot.sources
    ]
    current_region_focus = latest_snapshot.region_focus
    updated_snapshot = LatestSignalsResponse(
        generated_at=datetime.now(latest_snapshot.generated_at.tzinfo),
        region_focus=derive_region_focus_from_assessment(
            assessment,
            fallback=current_region_focus,
        ),
        features=latest_snapshot.features.model_copy(
            update={
                "flight_anomaly": probability_to_signal_feature(assessment)
            }
        ),
        sources=updated_sources,
    )
    persisted_snapshot = store.save_signal_snapshot(updated_snapshot)
    refreshed_source = next(
        source for source in persisted_snapshot.sources if source.name == "OpenSky Network"
    )
    return OpenSkySignalRefreshResponse(
        source=refreshed_source,
        snapshot=persisted_snapshot,
        assessment=assessment,
    )


def refresh_gdelt_signal() -> GdeltSignalRefreshResponse:
    settings = get_settings()
    store = SignalStore(settings.database_url)
    latest_snapshot = get_or_create_latest_snapshot()
    refresh_result = _collect_single_source("GDELT")

    articles = parse_articles(refresh_result.observation.payload)
    assessment = GdeltStrikeAssessmentService(
        GdeltAssessmentConfig(
            api_url=settings.gdelt_ai_api_url,
            api_key=settings.gdelt_ai_api_key,
            model=settings.gdelt_ai_model,
            timeout_seconds=settings.gdelt_ai_timeout_seconds,
        )
    ).assess_articles(articles)

    store.save_source_observation(
        source_name=refresh_result.observation.source_name,
        collected_at=refresh_result.observation.collected_at,
        status=refresh_result.observation.status,
        payload=_gdelt_payload_with_assessment(
            refresh_result.observation.payload,
            assessment,
        ),
    )
    refreshed_source = SignalSource(
        name="GDELT",
        status=refresh_result.observation.status,
        mode=_mode_from_source_status(refresh_result.observation.status),
        last_checked_at=refresh_result.observation.collected_at,
    )
    updated_sources = [
        refreshed_source if source.name == "GDELT" else source
        for source in latest_snapshot.sources
    ]
    updated_snapshot = LatestSignalsResponse(
        generated_at=max(
            [
                latest_snapshot.generated_at,
                refresh_result.observation.collected_at,
                *[
                    source.last_checked_at
                    for source in updated_sources
                    if source.last_checked_at is not None
                ],
            ]
        ),
        region_focus=derive_gdelt_region_focus_from_assessment(
            assessment,
            fallback=latest_snapshot.region_focus,
        ),
        features=latest_snapshot.features.model_copy(
            update={
                "news_volume": _gdelt_feature_value(
                    assessment=assessment,
                    heuristic_news_volume=compute_news_volume(articles),
                )
            }
        ),
        sources=updated_sources,
    )
    persisted_snapshot = store.save_signal_snapshot(updated_snapshot)
    refreshed_source = next(
        source for source in persisted_snapshot.sources if source.name == "GDELT"
    )
    return GdeltSignalRefreshResponse(
        source=refreshed_source,
        snapshot=persisted_snapshot,
        assessment=assessment,
    )


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
        observation = GdeltCollector(
            source_url=settings.gdelt_source_url,
            timeout_seconds=settings.gdelt_timeout_seconds,
        ).fetch_observation()
        store.save_source_observation(
            source_name="GDELT",
            collected_at=observation.collected_at,
            status=observation.status,
            payload=_gdelt_payload_for_storage(
                observation.raw_payload,
                observation.fallback_reason,
            ),
        )
        collected_at = observation.collected_at
        status = observation.status
        articles = observation.articles
        news_volume = observation.news_volume
        fallback_reason = observation.fallback_reason
    else:
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
    assessment = _gdelt_assessment_from_payload(latest["payload"]) if latest is not None else None
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
