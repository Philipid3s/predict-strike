import type {
  AlertEvaluationResponse,
  AlertHistoryResponse,
  FeatureVector,
  GdeltDetailResponse,
  GdeltSignalRefreshResponse,
  MarketOpportunitiesResponse,
  OpenSkyAnomaliesResponse,
  OpenSkySignalRefreshResponse,
  PizzaIndexSnapshotResponse,
  RiskScoreResponse,
  SignalSnapshot,
  SignalSourceRefreshResponse,
} from '../types/api';

const baseUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`.trim();

    try {
      const payload = await response.json();
      if (payload && typeof payload.detail === 'string') {
        detail = payload.detail;
      }
    } catch {
      // Ignore response parsing errors and fall back to the HTTP status.
    }

    throw new Error(`API request failed for ${path}: ${detail}`);
  }

  return (await response.json()) as T;
}

export function getLatestSignals(): Promise<SignalSnapshot> {
  return request<SignalSnapshot>('/api/v1/signals/latest');
}

export function refreshSignals(): Promise<SignalSnapshot> {
  return request<SignalSnapshot>('/api/v1/signals/refresh', { method: 'POST' });
}

export function refreshSignalSource(sourceName: string): Promise<SignalSourceRefreshResponse> {
  return request<SignalSourceRefreshResponse>('/api/v1/signals/refresh-source', {
    method: 'POST',
    body: JSON.stringify({ source_name: sourceName }),
  });
}

export function getLatestPizzaIndex(): Promise<PizzaIndexSnapshotResponse> {
  return request<PizzaIndexSnapshotResponse>('/api/v1/pizza-index/latest');
}

export function refreshPizzaIndex(): Promise<PizzaIndexSnapshotResponse> {
  return request<PizzaIndexSnapshotResponse>('/api/v1/pizza-index/refresh', { method: 'POST' });
}

export function getOpenSkyAnomalies(): Promise<OpenSkyAnomaliesResponse> {
  return request<OpenSkyAnomaliesResponse>('/api/v1/signals/sources/opensky-network/anomalies');
}

export function refreshOpenSkySignal(): Promise<OpenSkySignalRefreshResponse> {
  return request<OpenSkySignalRefreshResponse>('/api/v1/signals/sources/opensky-network/refresh-signal', {
    method: 'POST',
  });
}

export function getGdeltDetail(): Promise<GdeltDetailResponse> {
  return request<GdeltDetailResponse>('/api/v1/signals/sources/gdelt/detail');
}

export function refreshGdeltSignal(): Promise<GdeltSignalRefreshResponse> {
  return request<GdeltSignalRefreshResponse>('/api/v1/signals/sources/gdelt/refresh-signal', {
    method: 'POST',
  });
}

export function scoreRisk(features: FeatureVector): Promise<RiskScoreResponse> {
  return request<RiskScoreResponse>('/api/v1/risk/score', {
    method: 'POST',
    body: JSON.stringify({ features }),
  });
}

export function getMarketOpportunities(): Promise<MarketOpportunitiesResponse> {
  return request<MarketOpportunitiesResponse>('/api/v1/markets/opportunities');
}

export function getAlerts(): Promise<AlertHistoryResponse> {
  return request<AlertHistoryResponse>('/api/v1/alerts');
}

export function evaluateAlerts(): Promise<AlertEvaluationResponse> {
  return request<AlertEvaluationResponse>('/api/v1/alerts/evaluate', { method: 'POST' });
}
