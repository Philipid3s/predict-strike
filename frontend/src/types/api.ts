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
