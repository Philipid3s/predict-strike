import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const snapshotPayload = {
  generated_at: '2026-03-07T09:00:00Z',
  region_focus: '42-48N / 30-36E sector',
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
      name: 'NOTAM Feed',
      status: 'degraded',
      mode: 'fallback',
      last_checked_at: '2026-03-07T08:54:00Z',
    },
    {
      name: 'GDELT',
      status: 'active',
      mode: 'live',
      last_checked_at: '2026-03-07T08:50:00Z',
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
  breakdown: [
    { feature: 'flight_anomaly', value: 0.68, weight: 0.4, contribution: 0.272 },
    { feature: 'notam_spike', value: 0.34, weight: 0.2, contribution: 0.068 },
    { feature: 'news_volume', value: 0.57, weight: 0.2667, contribution: 0.152 },
    { feature: 'pizza_index', value: 0.46, weight: 0.1333, contribution: 0.0613 },
  ],
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
  upstream: 'gamma',
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

const pizzaIndexPayload = {
  generated_at: '2026-03-07T09:03:00Z',
  pizza_index: 0.46,
  pizza_index_confidence: 0.92,
  quality_summary: {
    full_count: 4,
    partial_count: 1,
    unavailable_count: 0,
  },
  targets: [
    {
      target_id: 'dominos_pentagon_city',
      display_name: "Domino's Pizza - Pentagon City",
      target_score: 0.66,
      weight: 1,
      data_quality: 'full',
      provider: 'pizzint',
    },
  ],
} as const;

const gdeltDetailPayload = {
  generated_at: '2026-03-07T09:04:30Z',
  status: 'active',
  news_volume: 0.57,
  article_count: 18,
  alert_article_count: 7,
  signal_article_count: 5,
  alert_share: 0.3889,
  volume_delta: null,
  freshness_score: 0.82,
  top_regions: [
    { label: 'Black Sea', count: 6 },
    { label: 'Eastern Mediterranean', count: 4 },
  ],
  top_themes: [
    { label: 'Conflict & strikes', count: 5 },
    { label: 'Mobilization & troop movement', count: 4 },
  ],
  top_sources: [
    { label: 'reuters.com', count: 3 },
    { label: 'apnews.com', count: 2 },
  ],
  headlines: [
    {
      article_id: 'GDELT-1',
      title: 'Regional air defense posture tightens after overnight incidents',
      url: 'https://example.com/headline-1',
      published_at: '2026-03-07T08:45:00Z',
      source: 'Reuters',
      source_label: 'reuters.com',
      is_alert: true,
      is_us_nato_actor: true,
      is_action_indicative: true,
      freshness_score: 0.88,
      themes: ['Conflict & strikes', 'Airspace & aviation disruption'],
      regions: ['Black Sea'],
    },
  ],
  assessment: {
    status: 'disabled',
    prompt_version: 'gdelt-strike-v1',
    probability_percent: null,
    target_region: null,
    target_country: null,
    summary: 'AI assessment is disabled because GDELT_AI_API_KEY or GDELT_AI_MODEL is not configured.',
    assessed_article_count: 5,
    freshness_score: 0.82,
  },
  provenance: {
    source_url_configured: true,
    keyword_watchlist: ['AIRSTRIKE', 'CONFLICT', 'MISSILE', 'MOBILIZATION', 'STRIKE', 'TROOPS'],
    theme_derivation: 'Keyword-derived from article title and body text.',
    region_derivation: 'Keyword-derived from article title and body text.',
    comparison_basis:
      'Signal refresh uses freshness-weighted, US/NATO-specific article selection with AI assessment; prior-window comparison is still unavailable.',
    collector_fallback_reason: null,
  },
} as const;

const refreshedGdeltSignalPayload = {
  source: {
    name: 'GDELT',
    status: 'active',
    mode: 'live',
    last_checked_at: '2026-03-07T09:08:00Z',
  },
  snapshot: {
    ...snapshotPayload,
    generated_at: '2026-03-07T09:08:00Z',
    region_focus: 'Eastern Mediterranean',
    features: {
      ...snapshotPayload.features,
      news_volume: 0.84,
    },
    sources: [
      snapshotPayload.sources[0],
      snapshotPayload.sources[1],
      {
        name: 'GDELT',
        status: 'active',
        mode: 'live',
        last_checked_at: '2026-03-07T09:08:00Z',
      },
      snapshotPayload.sources[3],
    ],
  },
  assessment: {
    status: 'ready',
    prompt_version: 'gdelt-strike-v1',
    probability_percent: 84,
    target_region: 'Eastern Mediterranean',
    target_country: 'Syria',
    summary: 'Recent US/NATO-linked strike coverage is clustering around Syria and nearby force-posture reporting.',
    assessed_article_count: 8,
    freshness_score: 0.91,
  },
} as const;

const refreshedGdeltDetailPayload = {
  ...gdeltDetailPayload,
  generated_at: '2026-03-07T09:08:10Z',
  news_volume: 0.84,
  freshness_score: 0.91,
  signal_article_count: 8,
  assessment: refreshedGdeltSignalPayload.assessment,
} as const;

const openSkyAnomaliesPayload = {
  generated_at: '2026-03-07T09:04:00Z',
  status: 'active',
  flight_anomaly: 0.68,
  assessment: {
    status: 'disabled',
    prompt_version: 'opensky-strike-v2',
    probability_percent: null,
    countries: [],
    explanation: 'AI assessment is disabled because OPENSKY_AI_API_KEY or OPENSKY_AI_MODEL is not configured.',
  },
  anomalies: [
    {
      icao24: 'abc123',
      callsign: 'RCH123',
      origin_country: 'United States',
      latitude: 44.12,
      longitude: 32.85,
      baro_altitude: 9750,
      velocity: 215,
      geo_altitude: 10100,
      reasons: [
        'military_like_callsign',
        'tanker_transport_pattern',
        'suspicious_region_concentration:42-48N / 30-36E sector',
        'military_callsign_cluster',
      ],
    },
  ],
} as const;

const refreshedSourcePayload = {
  source: {
    name: 'OpenSky Network',
    status: 'active',
    mode: 'live',
    last_checked_at: '2026-03-07T09:06:00Z',
  },
  snapshot: {
    ...snapshotPayload,
    generated_at: '2026-03-07T09:06:00Z',
    features: {
      ...snapshotPayload.features,
      flight_anomaly: 0.8,
    },
    sources: [
      {
        name: 'OpenSky Network',
        status: 'active',
        mode: 'live',
        last_checked_at: '2026-03-07T09:06:00Z',
      },
      snapshotPayload.sources[1],
    ],
  },
} as const;

const refreshedOpenSkySignalPayload = {
  source: {
    name: 'OpenSky Network',
    status: 'active',
    mode: 'live',
    last_checked_at: '2026-03-07T09:07:00Z',
  },
  snapshot: {
    ...snapshotPayload,
    generated_at: '2026-03-07T09:07:00Z',
    region_focus: 'Poland, Romania',
    features: {
      ...snapshotPayload.features,
      flight_anomaly: 0.91,
    },
    sources: [
      {
        name: 'OpenSky Network',
        status: 'active',
        mode: 'live',
        last_checked_at: '2026-03-07T09:07:00Z',
      },
      ...snapshotPayload.sources.slice(1),
    ],
  },
  assessment: {
    status: 'ready',
    prompt_version: 'opensky-strike-v2',
    probability_percent: 91,
    countries: ['Poland', 'Romania'],
    explanation: 'Military-adjacent traffic clustering keeps the AI strike signal elevated.',
  },
} as const;

const refreshedOpenSkyAnomaliesPayload = {
  ...openSkyAnomaliesPayload,
  generated_at: '2026-03-07T09:07:30Z',
  flight_anomaly: 0.91,
  assessment: refreshedOpenSkySignalPayload.assessment,
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

function getMetricLabels(ariaLabel: string) {
  const section = screen.getByLabelText(ariaLabel);
  return Array.from(section.querySelectorAll('.metric-card__label')).map((node) => node.textContent);
}

function getMetricValue(ariaLabel: string, label: string) {
  const section = screen.getByLabelText(ariaLabel);
  const cards = Array.from(section.querySelectorAll('.metric-card'));
  const metricCard = cards.find((card) => card.querySelector('.metric-card__label')?.textContent === label);

  return metricCard?.querySelector('.metric-card__value')?.textContent ?? null;
}

function getFeatureValue(label: string) {
  const featureTiles = Array.from(document.querySelectorAll('.feature-tile'));
  const featureTile = featureTiles.find((tile) => tile.querySelector('span')?.textContent === label);

  return featureTile?.querySelector('strong')?.textContent ?? null;
}

describe('App', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let riskScoreCallCount: number;
  let currentOpenSkyAnomaliesPayload: typeof openSkyAnomaliesPayload | typeof refreshedOpenSkyAnomaliesPayload;
  let currentGdeltDetailPayload: typeof gdeltDetailPayload | typeof refreshedGdeltDetailPayload;

  beforeEach(() => {
    riskScoreCallCount = 0;
    currentOpenSkyAnomaliesPayload = openSkyAnomaliesPayload;
    currentGdeltDetailPayload = gdeltDetailPayload;
    fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? 'GET';

        if (url.endsWith('/api/v1/signals/latest')) {
          return mockResponse(snapshotPayload);
        }

        if (url.endsWith('/api/v1/risk/score')) {
          riskScoreCallCount += 1;
          return mockResponse(
            riskScoreCallCount === 1
              ? riskPayload
              : {
                  ...riskPayload,
                  score: 0.51,
                },
          );
        }

        if (url.endsWith('/api/v1/signals/refresh-source') && method === 'POST') {
          return mockResponse(refreshedSourcePayload);
        }

        if (url.endsWith('/api/v1/signals/sources/opensky-network/refresh-signal') && method === 'POST') {
          currentOpenSkyAnomaliesPayload = refreshedOpenSkyAnomaliesPayload;
          return mockResponse(refreshedOpenSkySignalPayload);
        }

        if (url.endsWith('/api/v1/signals/sources/gdelt/refresh-signal') && method === 'POST') {
          currentGdeltDetailPayload = refreshedGdeltDetailPayload;
          return mockResponse(refreshedGdeltSignalPayload);
        }

        if (url.endsWith('/api/v1/markets/opportunities')) {
          return mockResponse(marketsPayload);
        }

        if (url.endsWith('/api/v1/pizza-index/latest') && method === 'GET') {
          return mockResponse(pizzaIndexPayload);
        }

        if (url.endsWith('/api/v1/signals/sources/gdelt/detail') && method === 'GET') {
          return mockResponse(currentGdeltDetailPayload);
        }

        if (url.endsWith('/api/v1/pizza-index/refresh') && method === 'POST') {
          return mockResponse(pizzaIndexPayload);
        }

        if (url.endsWith('/api/v1/signals/sources/opensky-network/anomalies') && method === 'GET') {
          return mockResponse(currentOpenSkyAnomaliesPayload);
        }

        if (url.endsWith('/api/v1/alerts') && method === 'GET') {
          return mockResponse(emptyAlertsPayload);
        }

        if (url.endsWith('/api/v1/alerts/evaluate') && method === 'POST') {
          return mockResponse(evaluatedAlertsPayload);
        }

        throw new Error(`Unhandled fetch request: ${method} ${url}`);
      });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    window.history.pushState({}, '', '/');
    vi.unstubAllGlobals();
  });

  it('loads the dashboard and updates alert history after evaluation', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();
    expect(getFeatureValue('OpenSky Network')).toBe('68%');
    expect(getFeatureValue('NOTAM Feed')).toBe('34%');
    expect(getFeatureValue('GDELT')).toBe('57%');
    expect(getFeatureValue('Pizza Index Activity')).toBe('46%');
    expect(screen.getByText(/Weight: 40%/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^Pizza Index Activity$/i).length).toBeGreaterThan(1);
    expect(screen.getByText(/No alerts recorded yet/i)).toBeInTheDocument();
    expect(screen.getByText(/Upstream gamma/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Will a direct strike occur in region X before June 2026\?/i).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Refresh source OpenSky Network/i })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /Refresh source Social OSINT/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Social OSINT/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Satellite Monitoring/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Dashboard$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^OpenSky Network$/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Evaluate Alerts/i }));

    await waitFor(() => expect(screen.getByText(/created 1 new alert/i)).toBeInTheDocument());

    expect(screen.getAllByText(/1 open/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/pol-001/i).length).toBeGreaterThan(0);
  });

  it('refreshes an individual source from the source list', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Refresh source OpenSky Network/i }));

    await waitFor(() =>
      expect(screen.getByText(/OpenSky Network refreshed from the latest collector check/i)).toBeInTheDocument(),
    );

    expect(screen.getByText(/51% Watch/i)).toBeInTheDocument();

    const refreshCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith('/api/v1/signals/refresh-source') &&
        (init?.method ?? 'GET') === 'POST',
    );

    expect(refreshCall).toBeTruthy();
    expect(refreshCall?.[1]?.body).toBe(JSON.stringify({ source_name: 'OpenSky Network' }));
  });

  it('navigates from the dashboard source card to the source detail page', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^OpenSky Network$/i }));

    expect(await screen.findByRole('heading', { name: /OpenSky Network/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Back to Dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Refresh Source$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Refresh Signal$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /All reasons/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Military-like callsign/i }));
    expect(screen.getByRole('button', { name: /Focus anomaly RCH123/i })).toHaveTextContent('RCH123');
    expect(screen.getByRole('button', { name: /Focus anomaly RCH123/i })).toHaveTextContent('United States · ICAO24 abc123');
    fireEvent.click(screen.getByRole('button', { name: /Focus anomaly RCH123/i }));
    expect(screen.getByText(/Focused on abc123 at 44.12, 32.85/i)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /World map of current OpenSky flight anomalies/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Reset View/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Open anomaly detail RCH123/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Callsign: RCH123/i)).toBeInTheDocument();
    expect(screen.getByText(/ICAO24: abc123/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Military-like callsign/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Tanker \/ transport pattern/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Open flight anomaly logic/i }));
    expect(screen.getAllByRole('dialog').length).toBeGreaterThan(1);
    expect(screen.getByText(/The current Flight Anomaly percentage is the latest AI probability/i)).toBeInTheDocument();
    expect(screen.getByText(/The collector still filters unusual flights using military-like callsigns/i)).toBeInTheDocument();
    expect(screen.getByText(/sends the condensed anomaly list to/i)).toBeInTheDocument();
    expect(screen.getByText(/the signal feature falls back to/i)).toBeInTheDocument();
    expect(getMetricLabels('OpenSky Network detail').slice(0, 2)).toEqual(['Status', 'Signal Feature']);
  });

  it('refreshes the OpenSky signal separately from the collector snapshot', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^OpenSky Network$/i }));

    expect(await screen.findByRole('heading', { name: /OpenSky Network/i })).toBeInTheDocument();
    expect(getMetricValue('OpenSky Network detail', 'Signal Feature')).toBe('68%');

    fireEvent.click(screen.getByRole('button', { name: /^Refresh Signal$/i }));

    await waitFor(() =>
      expect(screen.getByText(/OpenSky Network signal refreshed from the latest AI assessment/i)).toBeInTheDocument(),
    );

    expect(getMetricValue('OpenSky Network detail', 'Signal Feature')).toBe('91%');
    expect(screen.getByText(/AI Signal Assessment/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Poland, Romania/i })).toBeInTheDocument();
    expect(screen.getByText(/Status: Ready/i)).toBeInTheDocument();
    expect(screen.getByText(/Probability: 91%/i)).toBeInTheDocument();
    expect(screen.getByText(/Countries: Poland, Romania/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Explanation: Military-adjacent traffic clustering keeps the AI strike signal elevated/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Prompt version: opensky-strike-v2/i)).toBeInTheDocument();

    const refreshSignalCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith('/api/v1/signals/sources/opensky-network/refresh-signal') &&
        (init?.method ?? 'GET') === 'POST',
    );

    expect(refreshSignalCall).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Back to Dashboard/i }));

    expect(await screen.findByText(/51% Watch/i)).toBeInTheDocument();
  });

  it('opens the NOTAM detail page with a signal help affordance', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^NOTAM Feed$/i }));

    expect(await screen.findByRole('heading', { name: /NOTAM Feed/i })).toBeInTheDocument();
    expect(getMetricLabels('NOTAM Feed detail').slice(0, 2)).toEqual(['Status', 'Signal Feature']);

    fireEvent.click(screen.getByRole('button', { name: /Open NOTAM signal feature logic/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /NOTAM Spike Logic/i })).toBeInTheDocument();
    expect(screen.getByText(/normalized severity score built from the latest notice pull/i)).toBeInTheDocument();
    expect(screen.getByText(/Current NOTAM Spike/i)).toBeInTheDocument();
  });

  it('opens the Pizza Index detail page from the sidebar', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Pizza Index Activity$/i }));

    expect(await screen.findByRole('heading', { name: /Pizza Index Activity/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Confidence/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Domino's Pizza - Pentagon City/i)).toBeInTheDocument();
  });

  it('opens the GDELT detail page from the sidebar', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^GDELT$/i }));

    expect(await screen.findByRole('heading', { name: /GDELT/i })).toBeInTheDocument();
    expect(getMetricLabels('GDELT detail').slice(0, 2)).toEqual(['Status', 'Signal Feature']);
    expect(screen.getByText(/Freshness Score/i)).toBeInTheDocument();
    expect(screen.getByText(/Indicative Articles/i)).toBeInTheDocument();
    expect(screen.getByText(/Regional air defense posture tightens after overnight incidents/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Black Sea/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Conflict & strikes/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/reuters.com/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Open GDELT signal feature logic/i }));
    expect(screen.getByRole('heading', { name: /GDELT Strike Signal Logic/i })).toBeInTheDocument();
    expect(screen.getByText(/AI-derived media indicator built from a freshness-weighted set of recent articles/i)).toBeInTheDocument();
    expect(screen.getByText(/If the AI assessment is disabled, unavailable, or invalid/i)).toBeInTheDocument();
  });

  it('refreshes the GDELT signal separately from the collector snapshot', async () => {
    render(<App />);

    expect(await screen.findByText(/42% Watch/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^GDELT$/i }));

    expect(await screen.findByRole('heading', { name: /GDELT/i })).toBeInTheDocument();
    expect(getMetricValue('GDELT detail', 'Signal Feature')).toBe('57%');

    fireEvent.click(screen.getByRole('button', { name: /^Refresh Signal$/i }));

    await waitFor(() =>
      expect(screen.getByText(/GDELT signal refreshed from the latest AI assessment/i)).toBeInTheDocument(),
    );

    expect(getMetricValue('GDELT detail', 'Signal Feature')).toBe('84%');
    expect(screen.getByText(/AI Signal Assessment/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Eastern Mediterranean/i })).toBeInTheDocument();
    expect(screen.getByText(/Status: Ready/i)).toBeInTheDocument();
    expect(screen.getByText(/Probability: 84%/i)).toBeInTheDocument();
    expect(screen.getByText(/Target region: Eastern Mediterranean/i)).toBeInTheDocument();
    expect(screen.getByText(/Target country: Syria/i)).toBeInTheDocument();
    expect(screen.getByText(/Assessed articles: 8/i)).toBeInTheDocument();
    expect(screen.getByText(/Freshness: 91%/i)).toBeInTheDocument();
    expect(screen.getByText(/Summary: Recent US\/NATO-linked strike coverage is clustering around Syria/i)).toBeInTheDocument();
    expect(screen.getByText(/Prompt version: gdelt-strike-v1/i)).toBeInTheDocument();

    const refreshSignalCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith('/api/v1/signals/sources/gdelt/refresh-signal') &&
        (init?.method ?? 'GET') === 'POST',
    );

    expect(refreshSignalCall).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Back to Dashboard/i }));

    expect(await screen.findByText(/51% Watch/i)).toBeInTheDocument();
  });
});
