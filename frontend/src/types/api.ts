export interface FeatureVector {
  flight_anomaly: number;
  notam_spike: number;
  satellite_buildup: number;
  news_volume: number;
  osint_activity: number;
  pizza_index: number;
}

export type SourceMode = 'live' | 'fallback' | 'static_baseline';

export interface SignalSource {
  name: string;
  status: 'planned' | 'active' | 'degraded';
  mode: SourceMode;
  last_checked_at: string | null;
}

export interface SignalSnapshot {
  generated_at: string;
  region_focus: string;
  features: FeatureVector;
  sources: SignalSource[];
}

export interface SignalSourceRefreshResponse {
  source: SignalSource;
  snapshot: SignalSnapshot;
}

export interface OpenSkySignalAssessment {
  status: 'ready' | 'disabled' | 'error';
  prompt_version: string;
  probability_percent: number | null;
  countries: string[];
  explanation: string | null;
}

export interface OpenSkySignalRefreshResponse {
  source: SignalSource;
  snapshot: SignalSnapshot;
  assessment: OpenSkySignalAssessment;
}

export interface GdeltSignalAssessment {
  status: 'ready' | 'disabled' | 'error';
  prompt_version: string;
  probability_percent: number | null;
  target_region: string | null;
  target_country: string | null;
  summary: string;
  assessed_article_count: number;
  freshness_score: number;
}

export interface GdeltSignalRefreshResponse {
  source: SignalSource;
  snapshot: SignalSnapshot;
  assessment: GdeltSignalAssessment;
}

export interface PizzaIndexQualitySummary {
  full_count: number;
  partial_count: number;
  unavailable_count: number;
}

export interface PizzaIndexTargetContribution {
  target_id: string;
  display_name: string;
  target_score: number;
  weight: number;
  data_quality: 'full' | 'partial' | 'unavailable';
  provider: 'pizzint' | 'serpapi' | 'stub';
}

export interface PizzaIndexSnapshotResponse {
  generated_at: string;
  pizza_index: number;
  pizza_index_confidence: number;
  quality_summary: PizzaIndexQualitySummary;
  targets: PizzaIndexTargetContribution[];
}

export interface OpenSkyAnomaly {
  icao24: string;
  callsign: string | null;
  origin_country: string | null;
  latitude: number | null;
  longitude: number | null;
  baro_altitude: number | null;
  velocity: number | null;
  geo_altitude: number | null;
  reasons: string[];
}

export interface OpenSkyAnomaliesResponse {
  generated_at: string;
  status: 'planned' | 'active' | 'degraded';
  flight_anomaly: number;
  anomalies: OpenSkyAnomaly[];
  assessment: OpenSkySignalAssessment;
}

export interface GdeltRankedItem {
  label: string;
  count: number;
}

export interface GdeltHeadline {
  article_id: string;
  title: string;
  source: string | null;
  source_label: string;
  published_at: string | null;
  url: string | null;
  is_alert: boolean;
  is_us_nato_actor: boolean;
  is_action_indicative: boolean;
  freshness_score: number;
  themes: string[];
  regions: string[];
}

export interface GdeltProvenance {
  source_url_configured: boolean;
  keyword_watchlist: string[];
  theme_derivation: string;
  region_derivation: string;
  comparison_basis: string;
  collector_fallback_reason: string | null;
}

export interface GdeltDetailResponse {
  generated_at: string;
  status: 'planned' | 'active' | 'degraded';
  news_volume: number;
  article_count: number;
  alert_article_count: number;
  signal_article_count: number;
  freshness_score: number;
  alert_share: number;
  volume_delta: number | null;
  top_regions: GdeltRankedItem[];
  top_themes: GdeltRankedItem[];
  top_sources: GdeltRankedItem[];
  headlines: GdeltHeadline[];
  assessment: GdeltSignalAssessment;
  provenance: GdeltProvenance;
}

export interface RiskBreakdownItem {
  feature: keyof FeatureVector;
  value: number;
  weight: number;
  contribution: number;
}

export interface RiskThresholds {
  watch: number;
  alert: number;
}

export interface RiskScoreResponse {
  score: number;
  classification: 'monitor' | 'watch' | 'alert';
  breakdown: RiskBreakdownItem[];
  thresholds: RiskThresholds;
}

export interface MarketOpportunity {
  market_id: string;
  question: string;
  market_probability: number;
  model_probability: number;
  edge: number;
  signal: 'BUY' | 'SELL' | 'HOLD' | string;
}

export interface MarketOpportunitiesResponse {
  generated_at: string;
  source: SignalSource;
  upstream?: 'gamma' | 'pizzint' | 'bootstrap';
  opportunities: MarketOpportunity[];
}

export interface AlertRecord {
  id: string;
  created_at: string;
  market_id: string;
  question: string;
  market_probability: number;
  model_probability: number;
  edge: number;
  signal: 'BUY' | 'SELL' | 'HOLD' | string;
  status: 'open' | 'dismissed' | 'resolved';
}

export interface AlertHistoryResponse {
  generated_at: string;
  alerts: AlertRecord[];
}

export interface AlertEvaluationResponse {
  evaluated_at: string;
  created_count: number;
  alerts: AlertRecord[];
}
