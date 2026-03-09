import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const snapshotPayload = {
  generated_at: '2026-03-07T09:00:00Z',
  region_focus: 'global',
  features: {
    flight_anomaly: 0.68,
    notam_spike: 0.34,
    satellite_buildup: 0.21,
    news_volume: 0.57,
    osint_activity: 0.46,
    pizza_index: 0.12,
  },
  sources: [
    {
      name: 'OpenSky Network',
      status: 'active',
      mode: 'live',
      last_checked_at: '2026-03-07T08:55:00Z',
    },
    {
      name: 'Social OSINT',
      status: 'planned',
      mode: 'static_baseline',
      last_checked_at: null,
    },
  ],
} as const;

const riskPayload = {
  score: 0.42,
  classification: 'watch',
  breakdown: [],
  thresholds: {
    watch: 0.35,
    alert: 0.65,
  },
} as const;

const marketsPayload = {
  generated_at: '2026-03-07T09:01:00Z',
  source: {
    name: 'Polymarket',
    status: 'degraded',
    mode: 'fallback',
    last_checked_at: '2026-03-07T09:01:00Z',
  },
  opportunities: [
    {
      market_id: 'pol-001',
      question: 'Will a direct strike occur in region X before June 2026?',
      market_probability: 0.31,
      model_probability: 0.42,
      edge: 0.11,
      signal: 'BUY',
    },
  ],
} as const;

const emptyAlertsPayload = {
  generated_at: '2026-03-07T09:02:00Z',
  alerts: [],
} as const;

const evaluatedAlertsPayload = {
  evaluated_at: '2026-03-07T09:05:00Z',
  created_count: 1,
  alerts: [
    {
      id: 'alert-001',
      created_at: '2026-03-07T09:05:00Z',
      market_id: 'pol-001',
      question: 'Will a direct strike occur in region X before June 2026?',
      market_probability: 0.31,
      model_probability: 0.42,
      edge: 0.11,
      signal: 'BUY',
      status: 'open',
    },
  ],
} as const;

function mockResponse(payload: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => payload,
  });
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? 'GET';

        if (url.endsWith('/api/v1/signals/latest')) {
          return mockResponse(snapshotPayload);
        }

        if (url.endsWith('/api/v1/risk/score')) {
          return mockResponse(riskPayload);
        }

        if (url.endsWith('/api/v1/markets/opportunities')) {
          return mockResponse(marketsPayload);
        }

        if (url.endsWith('/api/v1/alerts') && method === 'GET') {
          return mockResponse(emptyAlertsPayload);
        }

        if (url.endsWith('/api/v1/alerts/evaluate') && method === 'POST') {
          return mockResponse(evaluatedAlertsPayload);
        }

        throw new Error(`Unhandled fetch request: ${method} ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads the dashboard and updates alert history after evaluation', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();
    expect(screen.getByText(/No alerts recorded yet/i)).toBeInTheDocument();
    expect(screen.getByText(/Data mode: Live/i)).toBeInTheDocument();
    expect(screen.getByText(/Data mode: Static Baseline/i)).toBeInTheDocument();
    expect(screen.getByText(/Source Fallback/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Will a direct strike occur in region X before June 2026\?/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /Evaluate Alerts/i }));

    await waitFor(() => expect(screen.getByText(/created 1 new alert/i)).toBeInTheDocument());

    expect(screen.getAllByText(/1 open/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/pol-001/i).length).toBeGreaterThan(0);
  });
});
