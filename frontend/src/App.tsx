import { useCallback, useEffect, useMemo, useState } from 'react';
import { MetricCard } from './components/MetricCard';
import { SectionCard } from './components/SectionCard';
import { StatusBadge } from './components/StatusBadge';
import {
  evaluateAlerts,
  getAlerts,
  getLatestSignals,
  getMarketOpportunities,
  refreshSignals,
  scoreRisk,
} from './services/api';
import type {
  AlertRecord,
  FeatureVector,
  MarketOpportunity,
  RiskScoreResponse,
  SourceMode,
  SignalSnapshot,
} from './types/api';
import { formatDateTime, formatPercent, formatSignedPoints, labelizeFeature, titleCase } from './utils/format';

interface DashboardState {
  signals: SignalSnapshot | null;
  risk: RiskScoreResponse | null;
  opportunities: MarketOpportunity[];
  marketsGeneratedAt: string | null;
  marketSource: SignalSnapshot['sources'][number] | null;
  alerts: AlertRecord[];
  alertsTimestamp: string | null;
}

const EMPTY_STATE: DashboardState = {
  signals: null,
  risk: null,
  opportunities: [],
  marketsGeneratedAt: null,
  marketSource: null,
  alerts: [],
  alertsTimestamp: null,
};

function getSourceTone(status: SignalSnapshot['sources'][number]['status']) {
  switch (status) {
    case 'active':
      return 'positive';
    case 'degraded':
      return 'warning';
    default:
      return 'neutral';
  }
}

function getSourceModeTone(mode: SourceMode) {
  switch (mode) {
    case 'live':
      return 'positive';
    case 'fallback':
      return 'warning';
    default:
      return 'neutral';
  }
}

function formatSourceMode(mode: SourceMode) {
  switch (mode) {
    case 'static_baseline':
      return 'Static Baseline';
    default:
      return titleCase(mode);
  }
}

function getAlertTone(status: AlertRecord['status']) {
  switch (status) {
    case 'open':
      return 'danger';
    case 'resolved':
      return 'positive';
    default:
      return 'neutral';
  }
}

function getClassificationTone(classification: RiskScoreResponse['classification']) {
  switch (classification) {
    case 'alert':
      return 'danger';
    case 'watch':
      return 'warning';
    default:
      return 'info';
  }
}

function getOpportunityTone(signal: string) {
  if (signal === 'BUY') {
    return 'positive';
  }

  if (signal === 'SELL') {
    return 'warning';
  }

  return 'neutral';
}

export default function App() {
  const [dashboard, setDashboard] = useState<DashboardState>(EMPTY_STATE);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const hydrateDashboard = useCallback(async (snapshot: SignalSnapshot) => {
    const [risk, markets, alertHistory] = await Promise.all([
      scoreRisk(snapshot.features),
      getMarketOpportunities(),
      getAlerts(),
    ]);

    setDashboard({
      signals: snapshot,
      risk,
      opportunities: markets.opportunities,
      marketsGeneratedAt: markets.generated_at,
      marketSource: markets.source,
      alerts: alertHistory.alerts,
      alertsTimestamp: alertHistory.generated_at,
    });
  }, []);

  const loadDashboard = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const snapshot = await getLatestSignals();
      await hydrateDashboard(snapshot);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load dashboard data.');
    } finally {
      setIsLoading(false);
    }
  }, [hydrateDashboard]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const handleRefreshSignals = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    setActionMessage(null);

    try {
      const snapshot = await refreshSignals();
      await hydrateDashboard(snapshot);
      setActionMessage('Signals refreshed from the latest collector pass.');
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Failed to refresh signals.');
    } finally {
      setIsRefreshing(false);
    }
  }, [hydrateDashboard]);

  const handleEvaluateAlerts = useCallback(async () => {
    setIsEvaluating(true);
    setError(null);
    setActionMessage(null);

    try {
      const [evaluation, markets] = await Promise.all([evaluateAlerts(), getMarketOpportunities()]);

      setDashboard((current) => ({
        ...current,
        opportunities: markets.opportunities,
        marketsGeneratedAt: markets.generated_at,
        marketSource: markets.source,
        alerts: evaluation.alerts,
        alertsTimestamp: evaluation.evaluated_at,
      }));

      setActionMessage(
        evaluation.created_count > 0
          ? `Evaluated opportunities and created ${evaluation.created_count} new alert${evaluation.created_count === 1 ? '' : 's'}.`
          : 'Evaluated opportunities with no new alerts created.',
      );
    } catch (evaluateError) {
      setError(evaluateError instanceof Error ? evaluateError.message : 'Failed to evaluate alerts.');
    } finally {
      setIsEvaluating(false);
    }
  }, []);

  const topOpportunity = useMemo(() => {
    return dashboard.opportunities.reduce<MarketOpportunity | null>((best, current) => {
      if (!best || Math.abs(current.edge) > Math.abs(best.edge)) {
        return current;
      }

      return best;
    }, null);
  }, [dashboard.opportunities]);

  const openAlerts = useMemo(() => dashboard.alerts.filter((alert) => alert.status === 'open'), [dashboard.alerts]);

  const featureEntries = useMemo(() => {
    if (!dashboard.signals) {
      return [];
    }

    return Object.entries(dashboard.signals.features) as Array<[keyof FeatureVector, number]>;
  }, [dashboard.signals]);

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Predict Strike</p>
          <h1>Operator Dashboard</h1>
          <p className="hero__subtitle">
            Monitor current OSINT indicators, source health, alert history, and Polymarket opportunities from one
            view.
          </p>
        </div>
        <div className="hero__actions">
          <button className="button button--secondary" onClick={() => void loadDashboard()} disabled={isLoading}>
            {isLoading ? 'Loading…' : 'Reload Dashboard'}
          </button>
          <button className="button" onClick={() => void handleRefreshSignals()} disabled={isRefreshing || isLoading}>
            {isRefreshing ? 'Refreshing…' : 'Refresh Signals'}
          </button>
          <button
            className="button button--accent"
            onClick={() => void handleEvaluateAlerts()}
            disabled={isEvaluating || isLoading}
          >
            {isEvaluating ? 'Evaluating…' : 'Evaluate Alerts'}
          </button>
        </div>
      </header>

      {error ? (
        <div className="notice notice--error" role="alert">
          {error}
        </div>
      ) : null}

      {actionMessage ? <div className="notice notice--success">{actionMessage}</div> : null}

      {isLoading && !dashboard.signals ? (
        <section className="loading-state">
          <p>Loading the latest snapshot, risk score, opportunities, and alert history…</p>
        </section>
      ) : null}

      {!isLoading && dashboard.signals && dashboard.risk ? (
        <>
          <section className="metric-grid" aria-label="Main indicators">
            <MetricCard
              label="Current Risk"
              value={`${formatPercent(dashboard.risk.score)} ${titleCase(dashboard.risk.classification)}`}
              detail={`Region focus: ${dashboard.signals.region_focus}`}
              accent={
                <StatusBadge tone={getClassificationTone(dashboard.risk.classification)}>
                  {titleCase(dashboard.risk.classification)}
                </StatusBadge>
              }
            />
            <MetricCard
              label="Open Alerts"
              value={`${openAlerts.length} open`}
              detail={`${dashboard.alerts.length} total in history`}
            />
            <MetricCard
              label="Top Market Edge"
              value={topOpportunity ? formatSignedPoints(topOpportunity.edge) : 'No opportunities'}
              detail={topOpportunity ? topOpportunity.question : 'Evaluate market data to surface edges.'}
              accent={
                topOpportunity ? (
                  <StatusBadge tone={getOpportunityTone(topOpportunity.signal)}>{topOpportunity.signal}</StatusBadge>
                ) : undefined
              }
            />
            <MetricCard
              label="Latest Activity"
              value={formatDateTime(dashboard.signals.generated_at)}
              detail={`Alerts updated ${formatDateTime(dashboard.alertsTimestamp)}`}
            />
          </section>

          <div className="dashboard-grid">
            <SectionCard
              title="Feature Snapshot"
              subtitle={`Snapshot captured ${formatDateTime(dashboard.signals.generated_at)}`}
            >
              <div className="feature-grid">
                {featureEntries.map(([feature, value]) => (
                  <div key={feature} className="feature-tile">
                    <span>{labelizeFeature(feature)}</span>
                    <strong>{formatPercent(value)}</strong>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="Per-Source Status" subtitle="Collector health from the latest normalized snapshot">
              <div className="source-list">
                {dashboard.signals.sources.map((source) => (
                  <article key={source.name} className="source-card">
                    <div className="source-card__title">
                      <h3>{source.name}</h3>
                      <div>
                        <StatusBadge tone={getSourceTone(source.status)}>{titleCase(source.status)}</StatusBadge>{' '}
                        <StatusBadge tone={getSourceModeTone(source.mode)}>{formatSourceMode(source.mode)}</StatusBadge>
                      </div>
                    </div>
                    <p>Data mode: {formatSourceMode(source.mode)}</p>
                    <p>Last checked: {formatDateTime(source.last_checked_at)}</p>
                  </article>
                ))}
              </div>
            </SectionCard>

            <SectionCard
              title="Alert History"
              subtitle={`Last evaluation ${formatDateTime(dashboard.alertsTimestamp)}`}
              action={<span className="section-card__meta">{openAlerts.length} open alerts</span>}
            >
              {dashboard.alerts.length === 0 ? (
                <p className="empty-state">No alerts recorded yet. Run an evaluation to create analyst alerts.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Created</th>
                        <th>Market</th>
                        <th>Signal</th>
                        <th>Status</th>
                        <th>Edge</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.alerts.map((alert) => (
                        <tr key={alert.id}>
                          <td>{formatDateTime(alert.created_at)}</td>
                          <td>
                            <div className="table-question">
                              <strong>{alert.market_id}</strong>
                              <span>{alert.question}</span>
                            </div>
                          </td>
                          <td>
                            <StatusBadge tone={getOpportunityTone(alert.signal)}>{alert.signal}</StatusBadge>
                          </td>
                          <td>
                            <StatusBadge tone={getAlertTone(alert.status)}>{titleCase(alert.status)}</StatusBadge>
                          </td>
                          <td>{formatSignedPoints(alert.edge)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>

            <SectionCard
              title="Polymarket Opportunities"
              subtitle={`Market snapshot ${formatDateTime(dashboard.marketsGeneratedAt)}`}
              action={
                <span className="section-card__meta">
                  {dashboard.opportunities.length} tracked markets · Source{' '}
                  {dashboard.marketSource ? formatSourceMode(dashboard.marketSource.mode) : 'Unknown'}
                </span>
              }
            >
              {dashboard.opportunities.length === 0 ? (
                <p className="empty-state">No market opportunities are currently available.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Question</th>
                        <th>Signal</th>
                        <th>Market</th>
                        <th>Model</th>
                        <th>Edge</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.opportunities.map((opportunity) => (
                        <tr key={opportunity.market_id}>
                          <td className="table-question">
                            <strong>{opportunity.market_id}</strong>
                            <span>{opportunity.question}</span>
                          </td>
                          <td>
                            <StatusBadge tone={getOpportunityTone(opportunity.signal)}>{opportunity.signal}</StatusBadge>
                          </td>
                          <td>{formatPercent(opportunity.market_probability)}</td>
                          <td>{formatPercent(opportunity.model_probability)}</td>
                          <td>{formatSignedPoints(opportunity.edge)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>
          </div>
        </>
      ) : null}
    </main>
  );
}
