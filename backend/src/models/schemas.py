from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ScoreClassification = Literal["monitor", "watch", "alert"]
TradeSignal = Literal["BUY", "SELL", "HOLD"]
SourceStatus = Literal["planned", "active", "degraded"]
SourceMode = Literal["live", "fallback", "static_baseline"]
MarketUpstream = Literal["gamma", "pizzint", "bootstrap"]
AlertStatus = Literal["open", "dismissed", "resolved"]
PizzaIndexDataQuality = Literal["full", "partial", "unavailable"]
PizzaIndexProvider = Literal["pizzint", "serpapi", "stub"]
PizzaIndexProviderMode = Literal["primary", "fallback", "stub"]
OpenSkyAssessmentStatus = Literal["ready", "disabled", "error"]
GdeltAssessmentStatus = Literal["ready", "disabled", "error"]


class FeatureSet(BaseModel):
    flight_anomaly: float = Field(..., ge=0.0, le=1.0)
    notam_spike: float = Field(..., ge=0.0, le=1.0)
    satellite_buildup: float = Field(..., ge=0.0, le=1.0)
    news_volume: float = Field(..., ge=0.0, le=1.0)
    osint_activity: float = Field(..., ge=0.0, le=1.0)
    pizza_index: float = Field(..., ge=0.0, le=1.0)


class WeightOverrides(BaseModel):
    flight_anomaly: float | None = Field(default=None, ge=0.0, le=1.0)
    notam_spike: float | None = Field(default=None, ge=0.0, le=1.0)
    satellite_buildup: float | None = Field(default=None, ge=0.0, le=1.0)
    news_volume: float | None = Field(default=None, ge=0.0, le=1.0)
    osint_activity: float | None = Field(default=None, ge=0.0, le=1.0)
    pizza_index: float | None = Field(default=None, ge=0.0, le=1.0)


class RiskScoreRequest(BaseModel):
    features: FeatureSet
    weights: WeightOverrides | None = None


class RiskContribution(BaseModel):
    feature: str
    value: float
    weight: float
    contribution: float


class RiskThresholds(BaseModel):
    watch: float
    alert: float


class RiskScoreResponse(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    classification: ScoreClassification
    breakdown: list[RiskContribution]
    thresholds: RiskThresholds


class SignalSource(BaseModel):
    name: str
    status: SourceStatus
    mode: SourceMode
    last_checked_at: datetime | None = None


class LatestSignalsResponse(BaseModel):
    generated_at: datetime
    region_focus: str
    features: FeatureSet
    sources: list[SignalSource]


class SignalSourceRefreshRequest(BaseModel):
    source_name: str


class SignalSourceRefreshResponse(BaseModel):
    source: SignalSource
    snapshot: LatestSignalsResponse


class OpenSkySignalRefreshResponse(BaseModel):
    source: SignalSource
    snapshot: LatestSignalsResponse
    assessment: "OpenSkyStrikeAssessment"


class GdeltSignalAssessment(BaseModel):
    status: GdeltAssessmentStatus
    prompt_version: str
    probability_percent: int | None = Field(default=None, ge=0, le=100)
    target_region: str | None = None
    target_country: str | None = None
    summary: str
    assessed_article_count: int = Field(..., ge=0)
    freshness_score: float = Field(..., ge=0.0, le=1.0)


class GdeltSignalRefreshResponse(BaseModel):
    source: SignalSource
    snapshot: LatestSignalsResponse
    assessment: GdeltSignalAssessment


class OpenSkyAnomaly(BaseModel):
    icao24: str
    callsign: str | None = None
    origin_country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    baro_altitude: float | None = None
    velocity: float | None = None
    geo_altitude: float | None = None
    reasons: list[str]


class OpenSkyStrikeAssessment(BaseModel):
    status: OpenSkyAssessmentStatus
    prompt_version: str
    probability_percent: int | None = Field(default=None, ge=0, le=100)
    countries: list[str]
    explanation: str | None = None


class OpenSkyAnomaliesResponse(BaseModel):
    generated_at: datetime
    status: SourceStatus
    flight_anomaly: float = Field(..., ge=0.0, le=1.0)
    anomalies: list[OpenSkyAnomaly]
    assessment: OpenSkyStrikeAssessment


class GdeltCountBreakdown(BaseModel):
    label: str
    count: int = Field(..., ge=0)


class GdeltHeadline(BaseModel):
    article_id: str
    title: str
    source: str | None = None
    source_label: str
    published_at: str | None = None
    url: str | None = None
    is_alert: bool
    is_us_nato_actor: bool
    is_action_indicative: bool
    freshness_score: float = Field(..., ge=0.0, le=1.0)
    themes: list[str]
    regions: list[str]


class GdeltProvenance(BaseModel):
    source_url_configured: bool
    keyword_watchlist: list[str]
    theme_derivation: str
    region_derivation: str
    comparison_basis: str
    collector_fallback_reason: str | None = None


class GdeltDetailResponse(BaseModel):
    generated_at: datetime
    status: SourceStatus
    news_volume: float = Field(..., ge=0.0, le=1.0)
    article_count: int = Field(..., ge=0)
    alert_article_count: int = Field(..., ge=0)
    signal_article_count: int = Field(..., ge=0)
    freshness_score: float = Field(..., ge=0.0, le=1.0)
    alert_share: float = Field(..., ge=0.0, le=1.0)
    volume_delta: float | None = None
    top_regions: list[GdeltCountBreakdown]
    top_themes: list[GdeltCountBreakdown]
    top_sources: list[GdeltCountBreakdown]
    headlines: list[GdeltHeadline]
    assessment: GdeltSignalAssessment
    provenance: GdeltProvenance


class MarketOpportunity(BaseModel):
    market_id: str
    question: str
    market_probability: float = Field(..., ge=0.0, le=1.0)
    model_probability: float = Field(..., ge=0.0, le=1.0)
    edge: float
    signal: TradeSignal


class MarketOpportunitiesResponse(BaseModel):
    generated_at: datetime
    source: SignalSource
    upstream: MarketUpstream
    opportunities: list[MarketOpportunity]


class PizzaIndexTarget(BaseModel):
    target_id: str
    display_name: str
    category: str
    priority_weight: float = Field(..., gt=0.0)
    location_cluster: str
    google_maps_url: str
    active: bool


class PizzaIndexTargetsResponse(BaseModel):
    generated_at: datetime
    targets: list[PizzaIndexTarget]


class PizzaIndexTargetActivity(BaseModel):
    target_id: str
    display_name: str
    provider: PizzaIndexProvider
    provider_mode: PizzaIndexProviderMode
    collected_at: datetime
    data_quality: PizzaIndexDataQuality
    capture_status: str
    is_open: bool | None = None
    current_busyness_percent: int | None = Field(default=None, ge=0, le=100)
    usual_busyness_percent: int | None = Field(default=None, ge=0, le=100)
    busyness_delta_percent: int | None = Field(default=None, ge=-100, le=100)
    current_busyness_label: str | None = None
    rating: float | None = Field(default=None, ge=0.0, le=5.0)
    reviews_count: int | None = Field(default=None, ge=0)
    address: str | None = None
    google_maps_url: str


class PizzaIndexQualitySummary(BaseModel):
    full_count: int = Field(..., ge=0)
    partial_count: int = Field(..., ge=0)
    unavailable_count: int = Field(..., ge=0)


class PizzaIndexTargetContribution(BaseModel):
    target_id: str
    display_name: str
    target_score: float = Field(..., ge=0.0, le=1.0)
    weight: float = Field(..., gt=0.0)
    data_quality: PizzaIndexDataQuality
    provider: PizzaIndexProvider


class PizzaIndexSnapshotResponse(BaseModel):
    generated_at: datetime
    pizza_index: float = Field(..., ge=0.0, le=1.0)
    pizza_index_confidence: float = Field(..., ge=0.0, le=1.0)
    quality_summary: PizzaIndexQualitySummary
    targets: list[PizzaIndexTargetContribution]


class AlertRecord(BaseModel):
    id: str
    created_at: datetime
    market_id: str
    question: str
    market_probability: float = Field(..., ge=0.0, le=1.0)
    model_probability: float = Field(..., ge=0.0, le=1.0)
    edge: float
    signal: TradeSignal
    status: AlertStatus


class AlertHistoryResponse(BaseModel):
    generated_at: datetime
    alerts: list[AlertRecord]


class AlertEvaluationResponse(BaseModel):
    evaluated_at: datetime
    created_count: int
    alerts: list[AlertRecord]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
