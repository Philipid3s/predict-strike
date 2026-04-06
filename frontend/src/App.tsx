import { useCallback, useEffect, useMemo, useState } from 'react';
import { MetricCard } from './components/MetricCard';
import { OpenSkyMap } from './components/OpenSkyMap';
import { SectionCard } from './components/SectionCard';
import { StatusBadge } from './components/StatusBadge';
import {
  evaluateAlerts,
  getGdeltDetail,
  getAlerts,
  getLatestPizzaIndex,
  getLatestSignals,
  getMarketOpportunities,
  getNotamDetail,
  getOpenSkyAnomalies,
  refreshGdeltSignal,
  refreshGdeltSource,
  refreshPizzaIndex,
  refreshOpenSkySignal,
  refreshOpenSkySource,
  refreshNotamSource,
  refreshSignalSource,
  refreshSignals,
  scoreRisk,
} from './services/api';
import { SOURCE_BY_ID, SOURCE_DEFINITIONS, SOURCE_ID_BY_NAME, type SourceDefinition } from './sourceRegistry';
import type {
  AlertRecord,
  FeatureVector,
  GdeltDetailResponse,
  GdeltSignalAssessment,
  MarketOpportunity,
  NotamDetailResponse,
  OpenSkyAnomaliesResponse,
  OpenSkySignalAssessment,
  PizzaIndexSnapshotResponse,
  RiskScoreResponse,
  SignalSnapshot,
  SignalSource,
  SourceMode,
} from './types/api';
import { formatDateTime, formatPercent, formatSignedPoints, labelizeFeature, titleCase } from './utils/format';

interface DashboardState {
  signals: SignalSnapshot | null;
  risk: RiskScoreResponse | null;
  opportunities: MarketOpportunity[];
  marketsGeneratedAt: string | null;
  marketSource: SignalSnapshot['sources'][number] | null;
  marketUpstream: string | null;
  alerts: AlertRecord[];
  alertsTimestamp: string | null;
}

interface AppRoute {
  page: 'dashboard' | 'source';
  sourceId?: string;
}

const EMPTY_STATE: DashboardState = {
  signals: null,
  risk: null,
  opportunities: [],
  marketsGeneratedAt: null,
  marketSource: null,
  marketUpstream: null,
  alerts: [],
  alertsTimestamp: null,
};

const PIZZA_INDEX_SOURCE_NAME = 'Pizza Index Activity';

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

function buildPizzaIndexSource(snapshot: PizzaIndexSnapshotResponse): SignalSource {
  const hasAnyCoverage =
    snapshot.quality_summary.full_count + snapshot.quality_summary.partial_count > 0;
  const hasCoverageGap =
    snapshot.quality_summary.partial_count > 0 || snapshot.quality_summary.unavailable_count > 0;

  return {
    name: PIZZA_INDEX_SOURCE_NAME,
    status: hasAnyCoverage ? (hasCoverageGap ? 'degraded' : 'active') : 'planned',
    mode: hasCoverageGap ? 'fallback' : 'live',
    last_checked_at: snapshot.generated_at,
  };
}

function mergePizzaIndexIntoSnapshot(
  snapshot: SignalSnapshot,
  pizzaSnapshot: PizzaIndexSnapshotResponse | null,
): SignalSnapshot {
  if (!pizzaSnapshot) {
    return snapshot;
  }

  const pizzaSource = buildPizzaIndexSource(pizzaSnapshot);
  const existingIndex = snapshot.sources.findIndex((source) => source.name === PIZZA_INDEX_SOURCE_NAME);
  const sources =
    existingIndex >= 0
      ? snapshot.sources.map((source, index) => (index === existingIndex ? pizzaSource : source))
      : [...snapshot.sources, pizzaSource];

  return {
    ...snapshot,
    features: {
      ...snapshot.features,
      pizza_index: pizzaSnapshot.pizza_index,
    },
    sources,
  };
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

function formatOpenSkyReason(reason: string) {
  if (reason === 'military_like_callsign') {
    return 'Military-like callsign';
  }

  if (reason === 'tanker_transport_pattern') {
    return 'Tanker / transport pattern';
  }

  if (reason === 'military_callsign_cluster') {
    return 'Military callsign cluster';
  }

  if (reason.startsWith('suspicious_region_concentration:')) {
    return `Suspicious region cluster: ${reason.split(':')[1]}`;
  }

  if (reason.startsWith('military_airfield_departure:')) {
    return `Departure near ${reason.split(':')[1]}`;
  }

  return titleCase(reason.replace(/_/g, ' '));
}

function formatNotamWindow(start: string | null, end: string | null) {
  if (start && end) {
    return `${formatDateTime(start)} to ${formatDateTime(end)}`;
  }
  if (start) {
    return `Starts ${formatDateTime(start)}`;
  }
  if (end) {
    return `Ends ${formatDateTime(end)}`;
  }
  return 'Window unavailable';
}

function hasCoordinates(latitude: number | null, longitude: number | null) {
  return latitude !== null && longitude !== null;
}

function parseRoute(pathname: string): AppRoute {
  if (pathname === '/' || pathname === '') {
    return { page: 'dashboard' };
  }

  const match = pathname.match(/^\/sources\/([^/]+)$/);
  if (match && SOURCE_BY_ID[match[1]]) {
    return { page: 'source', sourceId: match[1] };
  }

  return { page: 'dashboard' };
}

function buildSourcePath(sourceId: string) {
  return `/sources/${sourceId}`;
}

export default function App() {
  const [route, setRoute] = useState<AppRoute>(() => parseRoute(window.location.pathname));
  const [dashboard, setDashboard] = useState<DashboardState>(EMPTY_STATE);
  const [pizzaIndex, setPizzaIndex] = useState<PizzaIndexSnapshotResponse | null>(null);
  const [gdeltDetail, setGdeltDetail] = useState<GdeltDetailResponse | null>(null);
  const [notamDetail, setNotamDetail] = useState<NotamDetailResponse | null>(null);
  const [openSkyAnomalies, setOpenSkyAnomalies] = useState<OpenSkyAnomaliesResponse | null>(null);
  const [gdeltError, setGdeltError] = useState<string | null>(null);
  const [notamError, setNotamError] = useState<string | null>(null);
  const [pizzaError, setPizzaError] = useState<string | null>(null);
  const [openSkyError, setOpenSkyError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [refreshingSourceName, setRefreshingSourceName] = useState<string | null>(null);
  const [isRefreshingOpenSkySignal, setIsRefreshingOpenSkySignal] = useState(false);
  const [isRefreshingGdeltSignal, setIsRefreshingGdeltSignal] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [featureLogicSourceId, setFeatureLogicSourceId] = useState<'gdelt' | 'notam-feed' | 'opensky-network' | null>(null);
  const [selectedOpenSkyAnomalyId, setSelectedOpenSkyAnomalyId] = useState<string | null>(null);
  const [openSkyDetailAnomalyId, setOpenSkyDetailAnomalyId] = useState<string | null>(null);
  const [openSkyReasonFilter, setOpenSkyReasonFilter] = useState<string>('all');

  useEffect(() => {
    const handlePopState = () => setRoute(parseRoute(window.location.pathname));
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = useCallback((nextRoute: AppRoute) => {
    const nextPath = nextRoute.page === 'dashboard' ? '/' : buildSourcePath(nextRoute.sourceId!);
    if (window.location.pathname !== nextPath) {
      window.history.pushState({}, '', nextPath);
    }
    setRoute(nextRoute);
  }, []);

  const hydrateDashboard = useCallback(async (snapshot: SignalSnapshot, pizzaSnapshot: PizzaIndexSnapshotResponse | null = null) => {
    const mergedSnapshot = mergePizzaIndexIntoSnapshot(snapshot, pizzaSnapshot);
    const [risk, markets, alertHistory] = await Promise.all([
      scoreRisk(mergedSnapshot.features),
      getMarketOpportunities(),
      getAlerts(),
    ]);

    setDashboard({
      signals: mergedSnapshot,
      risk,
      opportunities: markets.opportunities,
      marketsGeneratedAt: markets.generated_at,
      marketSource: markets.source,
      marketUpstream: markets.upstream ?? null,
      alerts: alertHistory.alerts,
      alertsTimestamp: alertHistory.generated_at,
    });
  }, []);

  const loadDashboard = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [snapshot, latestPizzaIndex] = await Promise.all([
        getLatestSignals(),
        getLatestPizzaIndex().catch(() => null),
      ]);
      setPizzaIndex(latestPizzaIndex);
      await hydrateDashboard(snapshot, latestPizzaIndex);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load dashboard data.');
    } finally {
      setIsLoading(false);
    }
  }, [hydrateDashboard]);

  const loadPizzaIndex = useCallback(async () => {
    setPizzaError(null);
    try {
      const latest = await getLatestPizzaIndex();
      setPizzaIndex(latest);
    } catch (loadError) {
      setPizzaError(loadError instanceof Error ? loadError.message : 'Failed to load Pizza Index detail.');
    }
  }, []);

  const loadGdeltDetail = useCallback(async () => {
    setGdeltError(null);
    try {
      const latest = await getGdeltDetail();
      setGdeltDetail(latest);
      return latest;
    } catch (loadError) {
      setGdeltError(loadError instanceof Error ? loadError.message : 'Failed to load GDELT detail.');
      throw loadError;
    }
  }, []);

  const loadNotamDetail = useCallback(async () => {
    setNotamError(null);
    try {
      const latest = await getNotamDetail();
      setNotamDetail(latest);
      return latest;
    } catch (loadError) {
      setNotamError(loadError instanceof Error ? loadError.message : 'Failed to load NOTAM detail.');
      throw loadError;
    }
  }, []);

  const applyOpenSkyAnomalies = useCallback((latest: OpenSkyAnomaliesResponse) => {
    setOpenSkyAnomalies(latest);
    setSelectedOpenSkyAnomalyId(null);
    setOpenSkyDetailAnomalyId(null);
    setOpenSkyReasonFilter('all');
  }, []);

  const loadOpenSkyAnomalies = useCallback(async () => {
    setOpenSkyError(null);
    try {
      const latest = await getOpenSkyAnomalies();
      applyOpenSkyAnomalies(latest);
      return latest;
    } catch (loadError) {
      setOpenSkyError(loadError instanceof Error ? loadError.message : 'Failed to load OpenSky anomalies.');
      throw loadError;
    }
  }, [applyOpenSkyAnomalies]);

  const updateDashboardSnapshotRisk = useCallback(async (snapshot: SignalSnapshot) => {
    const risk = await scoreRisk(snapshot.features);
    setDashboard((current) => ({
      ...current,
      signals: snapshot,
      risk,
    }));
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (route.page === 'source' && route.sourceId === 'gdelt' && !gdeltDetail) {
      void loadGdeltDetail();
    }
    if (route.page === 'source' && route.sourceId === 'notam-feed' && !notamDetail) {
      void loadNotamDetail();
    }
    if (route.page === 'source' && route.sourceId === 'pizza-index-activity' && !pizzaIndex) {
      void loadPizzaIndex();
    }
    if (route.page === 'source' && route.sourceId === 'opensky-network' && !openSkyAnomalies) {
      void loadOpenSkyAnomalies();
    }
  }, [gdeltDetail, loadGdeltDetail, loadNotamDetail, loadOpenSkyAnomalies, loadPizzaIndex, notamDetail, openSkyAnomalies, pizzaIndex, route.page, route.sourceId]);

  useEffect(() => {
    if (route.page !== 'source' || route.sourceId !== 'opensky-network' || !openSkyAnomalies) {
      return;
    }

    const nextSelected =
      openSkyAnomalies.anomalies.find((anomaly) => anomaly.icao24 === selectedOpenSkyAnomalyId) ??
      openSkyAnomalies.anomalies.find((anomaly) => hasCoordinates(anomaly.latitude, anomaly.longitude)) ??
      openSkyAnomalies.anomalies[0] ??
      null;

    const nextSelectedId = nextSelected?.icao24 ?? null;
    if (nextSelectedId !== selectedOpenSkyAnomalyId) {
      setSelectedOpenSkyAnomalyId(nextSelectedId);
    }

    if (
      openSkyDetailAnomalyId &&
      !openSkyAnomalies.anomalies.some((anomaly) => anomaly.icao24 === openSkyDetailAnomalyId)
    ) {
      setOpenSkyDetailAnomalyId(null);
    }
  }, [openSkyAnomalies, openSkyDetailAnomalyId, route.page, route.sourceId, selectedOpenSkyAnomalyId]);

  const handleRefreshSignals = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    setActionMessage(null);

    try {
      const [snapshot, latestPizzaIndex] = await Promise.all([
        refreshSignals(),
        getLatestPizzaIndex().catch(() => null),
      ]);
      setPizzaIndex(latestPizzaIndex);
      await hydrateDashboard(snapshot, latestPizzaIndex);
      setActionMessage('Signals refreshed across OpenSky Network, NOTAM Feed, GDELT, and Pizza Index Activity.');
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
        marketUpstream: markets.upstream ?? null,
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

  const handleDashboardSourceRefresh = useCallback(async (sourceName: string) => {
    setRefreshingSourceName(sourceName);
    setError(null);
    setActionMessage(null);

    try {
      const refreshed = await refreshSignalSource(sourceName);
      let refreshedSnapshot = refreshed.snapshot;

      if (sourceName === 'OpenSky Network') {
        const latestAnomalies = await getOpenSkyAnomalies();
        applyOpenSkyAnomalies(latestAnomalies);
      } else if (sourceName === 'GDELT') {
        const latestDetail = await getGdeltDetail();
        setGdeltDetail(latestDetail);
      } else if (sourceName === PIZZA_INDEX_SOURCE_NAME) {
        const latestPizzaIndex = await getLatestPizzaIndex();
        setPizzaIndex(latestPizzaIndex);
        refreshedSnapshot = mergePizzaIndexIntoSnapshot(refreshed.snapshot, latestPizzaIndex);
      }

      await updateDashboardSnapshotRisk(refreshedSnapshot);
      setActionMessage(
        refreshed.source.status === 'degraded'
          ? `${sourceName} source refreshed with fallback data, and its signal snapshot was recomputed.`
          : `${sourceName} source and signal refreshed from the latest collector check.`,
      );
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : `Failed to refresh ${sourceName}.`);
    } finally {
      setRefreshingSourceName(null);
    }
  }, [applyOpenSkyAnomalies, updateDashboardSnapshotRisk]);

  const handleSourceDetailRefresh = useCallback(async (sourceName: string) => {
    setRefreshingSourceName(sourceName);
    setError(null);
    setGdeltError(null);
    setNotamError(null);
    setOpenSkyError(null);
    setPizzaError(null);
    setActionMessage(null);

    try {
      if (sourceName === 'OpenSky Network') {
        const refreshed = await refreshOpenSkySource();
        await updateDashboardSnapshotRisk(refreshed.snapshot);
        const latestAnomalies = await getOpenSkyAnomalies();
        applyOpenSkyAnomalies(latestAnomalies);
      } else if (sourceName === 'GDELT') {
        const refreshed = await refreshGdeltSource();
        await updateDashboardSnapshotRisk(refreshed.snapshot);
        const latestDetail = await getGdeltDetail();
        setGdeltDetail(latestDetail);
      } else if (sourceName === 'NOTAM Feed') {
        const refreshed = await refreshNotamSource();
        await updateDashboardSnapshotRisk(refreshed.snapshot);
        const latestDetail = await getNotamDetail();
        setNotamDetail(latestDetail);
      } else if (sourceName === PIZZA_INDEX_SOURCE_NAME) {
        const refreshed = await refreshPizzaIndex();
        setPizzaIndex(refreshed);
        if (dashboard.signals) {
          const mergedSnapshot = mergePizzaIndexIntoSnapshot(dashboard.signals, refreshed);
          await updateDashboardSnapshotRisk(mergedSnapshot);
        }
      }

      setActionMessage(
        sourceName === PIZZA_INDEX_SOURCE_NAME
          ? 'Pizza Index Activity source refreshed from the latest monitored targets.'
          : `${sourceName} source refreshed from the latest collector check.`,
      );
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : `Failed to refresh ${sourceName}.`);
    } finally {
      setRefreshingSourceName(null);
    }
  }, [applyOpenSkyAnomalies, dashboard.signals, updateDashboardSnapshotRisk]);

  const handleRefreshOpenSkySignal = useCallback(async () => {
    setIsRefreshingOpenSkySignal(true);
    setError(null);
    setOpenSkyError(null);
    setActionMessage(null);

    try {
      const refreshed = await refreshOpenSkySignal();
      await updateDashboardSnapshotRisk(refreshed.snapshot);
      const latestAnomalies = await getOpenSkyAnomalies();
      applyOpenSkyAnomalies(latestAnomalies);
      setActionMessage('OpenSky Network signal refreshed from the latest stored source snapshot.');
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Failed to refresh OpenSky Network signal.');
    } finally {
      setIsRefreshingOpenSkySignal(false);
    }
  }, [applyOpenSkyAnomalies, updateDashboardSnapshotRisk]);

  const handleRefreshGdeltSignal = useCallback(async () => {
    setIsRefreshingGdeltSignal(true);
    setError(null);
    setGdeltError(null);
    setActionMessage(null);

    try {
      const refreshed = await refreshGdeltSignal();
      await updateDashboardSnapshotRisk(refreshed.snapshot);
      const latestDetail = await getGdeltDetail();
      setGdeltDetail({
        ...latestDetail,
        assessment: latestDetail.assessment ?? refreshed.assessment,
      });
      setActionMessage('GDELT signal refreshed from the latest stored source snapshot.');
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Failed to refresh GDELT signal.');
    } finally {
      setIsRefreshingGdeltSignal(false);
    }
  }, [updateDashboardSnapshotRisk]);

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

  const dashboardSourceDefinitions = useMemo(
    () => SOURCE_DEFINITIONS.filter((source) => source.featureKey),
    [],
  );

  const dashboardFeatureEntries = useMemo(() => {
    if (!dashboard.signals || !dashboard.risk) {
      return [];
    }

    const signals = dashboard.signals;
    const risk = dashboard.risk;

    return dashboardSourceDefinitions.map((source) => ({
      featureKey: source.featureKey ?? null,
      id: source.id,
      label: source.name,
      summary: source.summary,
      value: source.featureKey ? signals.features[source.featureKey] : null,
      weight:
        source.featureKey
          ? risk.breakdown.find((item) => item.feature === source.featureKey)?.weight ?? null
          : null,
    }));
  }, [dashboard.risk, dashboard.signals, dashboardSourceDefinitions]);

  const dashboardSignalSources = useMemo(() => {
    if (!dashboard.signals) {
      return [];
    }

    return dashboard.signals.sources.filter((source) => SOURCE_ID_BY_NAME[source.name]);
  }, [dashboard.signals]);

  const currentSourceDefinition = route.page === 'source' && route.sourceId ? SOURCE_BY_ID[route.sourceId] : null;

  const currentSignalSource = useMemo(() => {
    if (!dashboard.signals || !currentSourceDefinition) {
      return null;
    }

    return dashboard.signals.sources.find((source) => source.name === currentSourceDefinition.name) ?? null;
  }, [currentSourceDefinition, dashboard.signals]);

  const selectedOpenSkyAnomaly = useMemo(() => {
    if (!openSkyAnomalies) {
      return null;
    }

    return openSkyAnomalies.anomalies.find((anomaly) => anomaly.icao24 === selectedOpenSkyAnomalyId) ?? null;
  }, [openSkyAnomalies, selectedOpenSkyAnomalyId]);

  const openSkyDetailAnomaly = useMemo(() => {
    if (!openSkyAnomalies) {
      return null;
    }

    return openSkyAnomalies.anomalies.find((anomaly) => anomaly.icao24 === openSkyDetailAnomalyId) ?? null;
  }, [openSkyAnomalies, openSkyDetailAnomalyId]);

  const openSkyReasonOptions = useMemo(() => {
    if (!openSkyAnomalies) {
      return [];
    }

    return Array.from(new Set(openSkyAnomalies.anomalies.flatMap((anomaly) => anomaly.reasons)));
  }, [openSkyAnomalies]);

  useEffect(() => {
    if (openSkyReasonFilter !== 'all' && !openSkyReasonOptions.includes(openSkyReasonFilter)) {
      setOpenSkyReasonFilter('all');
    }
  }, [openSkyReasonFilter, openSkyReasonOptions]);

  const renderFeatureLogicModal = () => {
    if (!featureLogicSourceId) {
      return null;
    }

    if (featureLogicSourceId === 'opensky-network') {
      return (
        <div className="modal-backdrop" role="presentation" onClick={() => setFeatureLogicSourceId(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="feature-logic-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal__header">
              <div>
                <p className="eyebrow">Help</p>
                <h2 id="feature-logic-title">Flight Anomaly Logic</h2>
              </div>
              <button className="button button--secondary button--inline" onClick={() => setFeatureLogicSourceId(null)}>
                Close
              </button>
            </div>
            <div className="detail-stack">
              <p>
                The current Flight Anomaly percentage is the latest AI probability returned from the OpenSky anomaly
                list. It is not derived directly from the collector rule points anymore.
              </p>
              <p>
                The collector still filters unusual flights using military-like callsigns, tanker or transport
                patterns, suspicious-region concentration, cluster behavior, and departures near tracked military
                airfields.
              </p>
              <p>
                `Refresh Source` updates that anomaly list only. `Refresh Signal` sends the condensed anomaly list to
                the AI model and stores the returned probability as the signal feature.
              </p>
              <p>
                If the AI response fails or cannot be parsed, the signal feature falls back to `0%` instead of using
                the old heuristic point score.
              </p>
              <div className="feature-tile feature-tile--active">
                <span>Current AI Flight Probability</span>
                <strong>
                  {typeof openSkyAnomalies?.assessment?.probability_percent === 'number'
                    ? formatPercent(openSkyAnomalies.assessment.probability_percent / 100)
                    : dashboard.signals
                      ? formatPercent(dashboard.signals.features.flight_anomaly)
                      : 'Unavailable'}
                </strong>
              </div>
            </div>
          </div>
        </div>
      );
    }

    if (featureLogicSourceId === 'notam-feed') {
      return (
        <div className="modal-backdrop" role="presentation" onClick={() => setFeatureLogicSourceId(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="feature-logic-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal__header">
              <div>
                <p className="eyebrow">Help</p>
                <h2 id="feature-logic-title">NOTAM Spike Logic</h2>
              </div>
              <button className="button button--secondary button--inline" onClick={() => setFeatureLogicSourceId(null)}>
                Close
              </button>
            </div>
            <div className="detail-stack">
              <p>
                The NOTAM Spike percentage is a normalized severity score built from the latest notice pull. It is not
                a simple count of all notices.
              </p>
              <p>
                The collector gives more weight to military-adjacent wording, restrictive-airspace language, and
                disruption-oriented notices than to routine advisory traffic.
              </p>
              <p>
                Clusters of high-signal notices push the percentage upward, then the final result is normalized into
                the same 0-100% range used by the other source features.
              </p>
              <div className="feature-tile feature-tile--active">
                <span>Current NOTAM Spike</span>
                <strong>
                  {dashboard.signals ? formatPercent(dashboard.signals.features.notam_spike) : 'Unavailable'}
                </strong>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="modal-backdrop" role="presentation" onClick={() => setFeatureLogicSourceId(null)}>
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="feature-logic-title"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="modal__header">
            <div>
              <p className="eyebrow">Help</p>
              <h2 id="feature-logic-title">GDELT Strike Signal Logic</h2>
            </div>
            <button className="button button--secondary button--inline" onClick={() => setFeatureLogicSourceId(null)}>
              Close
            </button>
          </div>
          <div className="detail-stack">
            <p>
              The GDELT percentage is an AI-derived media indicator built from a freshness-weighted set of recent
              articles, not a direct confirmation of a strike.
            </p>
            <p>
              The collector prioritizes current articles that mention US or NATO actors alongside strike-indicative
              language, then `Refresh Signal` sends that condensed article set to the AI assessment step.
            </p>
            <p>
              The returned probability is normalized into the `news_volume` feature slot for risk scoring, and the AI
              output can also identify a likely target region or country.
            </p>
            <p>
              `Refresh Source` still updates the article set and diagnostics only. `Refresh Signal` is the action that
              recalculates the AI-driven signal feature from the latest representative article corpus.
            </p>
            <p>
              If the AI assessment is disabled, unavailable, or invalid, the GDELT signal feature is set to `0%`
              instead of falling back to the raw article-volume heuristic.
            </p>
            <div className="feature-tile feature-tile--active">
              <span>Current GDELT Signal</span>
              <strong>
                {dashboard.signals ? formatPercent(dashboard.signals.features.news_volume) : 'Unavailable'}
              </strong>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderDashboard = () => (
    <>
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
            {isLoading ? 'Loading...' : 'Reload Dashboard'}
          </button>
          <button className="button" onClick={() => void handleRefreshSignals()} disabled={isRefreshing || isLoading}>
            {isRefreshing ? 'Refreshing...' : 'Refresh Signals'}
          </button>
          <button
            className="button button--accent"
            onClick={() => void handleEvaluateAlerts()}
            disabled={isEvaluating || isLoading}
          >
            {isEvaluating ? 'Evaluating...' : 'Evaluate Alerts'}
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
          <p>Loading the latest snapshot, risk score, opportunities, and alert history...</p>
        </section>
      ) : null}

      {!isLoading && dashboard.signals && dashboard.risk ? (
        <>
          <section className="metric-grid" aria-label="Main indicators">
            <MetricCard
              label="Current Risk"
              value={`${formatPercent(dashboard.risk.score)} ${titleCase(dashboard.risk.classification)}`}
              detail={`Suspicious region: ${dashboard.signals.region_focus}`}
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
                {dashboardFeatureEntries.map((feature) => (
                  <div key={feature.id} className="feature-tile feature-tile--dashboard">
                    <div className="feature-tile__copy">
                      <span>{feature.label}</span>
                      <p>{feature.summary}</p>
                      <p>
                        Weight: {feature.weight === null ? 'Unavailable' : formatPercent(feature.weight)}
                      </p>
                    </div>
                    <strong>{feature.value === null ? 'Unavailable' : formatPercent(feature.value)}</strong>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="Per-Source Status" subtitle="Collector health from the latest normalized snapshot">
              <div className="source-list">
                {dashboardSignalSources.map((source) => {
                  const sourceId = SOURCE_ID_BY_NAME[source.name];
                  const implementedSource = sourceId ? SOURCE_BY_ID[sourceId] : null;
                  return (
                    <article key={source.name} className="source-card">
                      <div className="source-card__title">
                        <div>
                          <h3>{source.name}</h3>
                          <div>
                            <StatusBadge tone={getSourceTone(source.status)}>{titleCase(source.status)}</StatusBadge>{' '}
                            <StatusBadge tone={getSourceModeTone(source.mode)}>{formatSourceMode(source.mode)}</StatusBadge>
                          </div>
                        </div>
                        <div className="source-card__actions">
                          <button
                            className="button button--inline button--secondary"
                            onClick={() => void handleDashboardSourceRefresh(source.name)}
                            disabled={isLoading || refreshingSourceName === source.name || source.mode === 'static_baseline'}
                            aria-label={`Refresh source ${source.name}`}
                          >
                            {refreshingSourceName === source.name
                              ? 'Refreshing...'
                              : source.mode !== 'static_baseline'
                                ? 'Refresh'
                                : 'Static'}
                          </button>
                        </div>
                      </div>
                      <p>{implementedSource?.summary ?? 'Planned baseline source in the normalized snapshot.'}</p>
                    </article>
                  );
                })}
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
                  {dashboard.opportunities.length} tracked markets
                  {dashboard.marketUpstream ? ` · Upstream ${dashboard.marketUpstream}` : ''}
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
    </>
  );

  const renderPizzaIndexDetail = (sourceDefinition: SourceDefinition) => (
    <>
      <header className="detail-hero">
        <div>
          <p className="eyebrow">Source Detail</p>
          <h1>{sourceDefinition.name}</h1>
          <p className="hero__subtitle">{sourceDefinition.detail}</p>
        </div>
        <div className="hero__actions">
          <button className="button button--secondary" onClick={() => navigate({ page: 'dashboard' })}>
            Back to Dashboard
          </button>
          <button
            className="button"
            onClick={() => void handleSourceDetailRefresh(sourceDefinition.name)}
            disabled={refreshingSourceName === sourceDefinition.name}
          >
            {refreshingSourceName === sourceDefinition.name ? 'Refreshing...' : 'Refresh Source'}
          </button>
        </div>
      </header>

      {pizzaError ? (
        <div className="notice notice--error" role="alert">
          {pizzaError}
        </div>
      ) : null}

      {actionMessage ? <div className="notice notice--success">{actionMessage}</div> : null}

      {!pizzaIndex ? (
        <section className="loading-state">
          <p>Loading Pizza Index detail...</p>
        </section>
      ) : (
        <>
          <section className="metric-grid" aria-label="Pizza Index detail">
            <MetricCard
              label="Pizza Index"
              value={formatPercent(pizzaIndex.pizza_index)}
              detail={`Generated ${formatDateTime(pizzaIndex.generated_at)}`}
            />
            <MetricCard
              label="Confidence"
              value={formatPercent(pizzaIndex.pizza_index_confidence)}
              detail="Aggregate snapshot confidence"
            />
            <MetricCard
              label="Full Targets"
              value={`${pizzaIndex.quality_summary.full_count}`}
              detail="Targets with full current activity"
            />
            <MetricCard
              label="Coverage Gaps"
              value={`${pizzaIndex.quality_summary.partial_count} fallback, ${pizzaIndex.quality_summary.unavailable_count} missing`}
              detail="Targets using fallback data or with no usable observation"
            />
          </section>

          <SectionCard
            title="Monitored Targets"
            subtitle={`Snapshot captured ${formatDateTime(pizzaIndex.generated_at)}`}
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Provider</th>
                    <th>Quality</th>
                    <th>Weight</th>
                    <th>Target Score</th>
                  </tr>
                </thead>
                <tbody>
                  {pizzaIndex.targets.map((target) => (
                    <tr key={target.target_id}>
                      <td className="table-question">
                        <strong>{target.target_id}</strong>
                        <span>{target.display_name}</span>
                      </td>
                      <td>{titleCase(target.provider)}</td>
                      <td>{titleCase(target.data_quality)}</td>
                      <td>{target.weight.toFixed(2)}</td>
                      <td>{formatPercent(target.target_score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </>
      )}
    </>
  );

  const renderGdeltDetail = (sourceDefinition: SourceDefinition, source: SignalSource | null) => {
    const gdeltAssessment: GdeltSignalAssessment | null = gdeltDetail?.assessment ?? null;
    const gdeltCollectorFallbackReason = gdeltDetail?.provenance.collector_fallback_reason ?? null;
    const featureValue =
      gdeltAssessment
        ? typeof gdeltAssessment.probability_percent === 'number'
          ? gdeltAssessment.probability_percent / 100
          : sourceDefinition.featureKey && dashboard.signals
            ? dashboard.signals.features[sourceDefinition.featureKey]
            : 0
        : gdeltDetail?.news_volume ??
          (sourceDefinition.featureKey && dashboard.signals ? dashboard.signals.features[sourceDefinition.featureKey] : null);

    return (
      <>
        <header className="detail-hero">
          <div>
            <p className="eyebrow">Source Detail</p>
            <h1>{sourceDefinition.name}</h1>
            <p className="hero__subtitle">{sourceDefinition.detail}</p>
          </div>
          <div className="hero__actions">
            <button className="button button--secondary" onClick={() => navigate({ page: 'dashboard' })}>
              Back to Dashboard
            </button>
            <button
              className="button"
              onClick={() => void handleSourceDetailRefresh(sourceDefinition.name)}
              disabled={refreshingSourceName === sourceDefinition.name || isRefreshingGdeltSignal}
            >
              {refreshingSourceName === sourceDefinition.name ? 'Refreshing...' : 'Refresh Source'}
            </button>
            <button
              className="button button--secondary"
              onClick={() => void handleRefreshGdeltSignal()}
              disabled={isRefreshingGdeltSignal || refreshingSourceName === sourceDefinition.name}
            >
              {isRefreshingGdeltSignal ? 'Refreshing Signal...' : 'Refresh Signal'}
            </button>
          </div>
        </header>

        {error ? (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        ) : null}

        {gdeltError ? (
          <div className="notice notice--error" role="alert">
            {gdeltError}
          </div>
        ) : null}

        {actionMessage ? <div className="notice notice--success">{actionMessage}</div> : null}

        {!gdeltDetail ? (
          <section className="loading-state">
            <p>Loading GDELT detail...</p>
          </section>
          ) : (
          <>
            <section className="metric-grid" aria-label="GDELT detail">
              <MetricCard
                label="Status"
                value={source ? titleCase(source.status) : titleCase(gdeltDetail.status)}
                detail={
                  gdeltCollectorFallbackReason
                    ? `Mode ${formatSourceMode(source?.mode ?? 'fallback')} - Fallback reason: ${gdeltCollectorFallbackReason}`
                    : source
                      ? `Mode ${formatSourceMode(source.mode)}`
                      : 'Dedicated GDELT detail snapshot'
                }
                accent={
                  source ? <StatusBadge tone={getSourceTone(source.status)}>{titleCase(source.status)}</StatusBadge> : undefined
                }
              />
              <MetricCard
                label="Signal Feature"
                value={featureValue === null ? 'Unavailable' : formatPercent(featureValue)}
                detail={
                  typeof gdeltAssessment?.probability_percent === 'number'
                    ? 'Current AI probability returned by Refresh Signal.'
                    : 'Normalized GDELT signal feature from the latest article snapshot.'
                }
                action={
                  <button
                    className="icon-help-button"
                    onClick={() => setFeatureLogicSourceId('gdelt')}
                    aria-label="Open GDELT signal feature logic"
                    title="GDELT Signal Feature Logic"
                  >
                    ?
                  </button>
                }
              />
              <MetricCard
                label="Freshness Score"
                value={
                  typeof gdeltDetail.freshness_score === 'number'
                    ? formatPercent(gdeltDetail.freshness_score)
                    : 'Unavailable'
                }
                detail="How recent the representative article set is right now"
              />
              <MetricCard
                label="Indicative Articles"
                value={
                  `${gdeltDetail.signal_article_count}`
                }
                detail={
                  gdeltDetail.article_count > 0
                    ? `${formatPercent(gdeltDetail.signal_article_count / gdeltDetail.article_count)} of current articles matched the US/NATO strike-indicative filter`
                    : 'No current articles matched the US/NATO strike-indicative filter'
                }
              />
            </section>

            <div className="dashboard-grid dashboard-grid--detail">
              <SectionCard
                title="AI Signal Assessment"
                subtitle={`Latest AI signal pass ${formatDateTime(dashboard.signals?.generated_at ?? source?.last_checked_at)}`}
              >
                <div className="opensky-assessment-card">
                  <div className="opensky-assessment-card__hero">
                    <div>
                      <p className="opensky-assessment-card__eyebrow">Likely Target</p>
                      <h3>
                        {gdeltAssessment?.target_country ?? gdeltAssessment?.target_region ?? 'Unknown'}
                      </h3>
                    </div>
                    <div className="opensky-assessment-card__metric">
                      <span>Last Checked</span>
                      <strong>{source ? formatDateTime(source.last_checked_at) : 'Unavailable'}</strong>
                    </div>
                  </div>
                  {gdeltAssessment ? (
                    <div className="detail-stack">
                      <p>Status: {gdeltAssessment.status ? titleCase(gdeltAssessment.status) : 'Unavailable'}</p>
                      <p>
                        Probability:{' '}
                        {typeof gdeltAssessment.probability_percent === 'number'
                          ? formatPercent(gdeltAssessment.probability_percent / 100)
                          : 'Unavailable'}
                      </p>
                      <p>Target region: {gdeltAssessment.target_region ?? 'Unavailable'}</p>
                      <p>
                        Target country: {gdeltAssessment.target_country ?? 'Unavailable'}
                      </p>
                      <p>Assessed articles: {gdeltAssessment.assessed_article_count}</p>
                      <p>Freshness: {formatPercent(gdeltAssessment.freshness_score)}</p>
                      <p>Summary: {gdeltAssessment.summary}</p>
                      {gdeltCollectorFallbackReason ? (
                        <p>Collector fallback reason: {gdeltCollectorFallbackReason}</p>
                      ) : null}
                      <p>Prompt version: {gdeltAssessment.prompt_version}</p>
                    </div>
                  ) : (
                    <p className="empty-state">No AI signal assessment is available for the current GDELT article snapshot.</p>
                  )}
                </div>
              </SectionCard>

              <SectionCard title="Top Regions" subtitle="Where coverage is concentrating">
                {gdeltDetail.top_regions.length === 0 ? (
                  <p className="empty-state">No regional concentration is available in the current GDELT snapshot.</p>
                ) : (
                  <div className="source-list">
                    {gdeltDetail.top_regions.map((region) => (
                      <article key={region.label} className="source-card">
                        <div className="source-card__title">
                          <h3>{region.label}</h3>
                          <StatusBadge tone="info">{`${region.count}`}</StatusBadge>
                        </div>
                        <p>Articles mapped to this region in the current GDELT pull.</p>
                      </article>
                    ))}
                  </div>
                )}
              </SectionCard>

              <SectionCard title="Top Themes" subtitle="Narratives driving the current score">
                {gdeltDetail.top_themes.length === 0 ? (
                  <p className="empty-state">No theme clustering is available in the current GDELT snapshot.</p>
                ) : (
                  <div className="source-list">
                    {gdeltDetail.top_themes.map((theme) => (
                      <article key={theme.label} className="source-card">
                        <div className="source-card__title">
                          <h3>{theme.label}</h3>
                          <StatusBadge tone="warning">{`${theme.count}`}</StatusBadge>
                        </div>
                        <p>Current matched articles grouped under this theme.</p>
                      </article>
                    ))}
                  </div>
                )}
              </SectionCard>

              <SectionCard title="Source Mix" subtitle="Domains contributing the most coverage">
                {gdeltDetail.top_sources.length === 0 ? (
                  <p className="empty-state">No source-domain mix is available in the current GDELT snapshot.</p>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Source</th>
                          <th>Articles</th>
                        </tr>
                      </thead>
                      <tbody>
                        {gdeltDetail.top_sources.map((sourceItem) => (
                          <tr key={sourceItem.label}>
                            <td>{sourceItem.label}</td>
                            <td>{sourceItem.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </SectionCard>
            </div>

            <SectionCard title="Recent Headlines" subtitle={`Snapshot captured ${formatDateTime(gdeltDetail.generated_at)}`}>
              {gdeltDetail.headlines.length === 0 ? (
                <p className="empty-state">No representative headlines are available in the current GDELT snapshot.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                        <tr>
                          <th>Headline</th>
                          <th>Source</th>
                          <th>Regions</th>
                          <th>Time</th>
                        </tr>
                      </thead>
                      <tbody>
                        {gdeltDetail.headlines.map((headline) => (
                          <tr key={headline.article_id}>
                            <td className="table-question">
                              <strong>{headline.title}</strong>
                              {headline.url ? <span>{headline.url}</span> : null}
                              <span>{headline.themes.length > 0 ? `Themes: ${headline.themes.join(', ')}` : 'Themes: n/a'}</span>
                            </td>
                          <td>{headline.source_label}</td>
                          <td>{headline.regions.length > 0 ? headline.regions.join(', ') : 'n/a'}</td>
                          <td>{headline.published_at ? formatDateTime(headline.published_at) : 'n/a'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>
          </>
        )}
      </>
    );
  };

  const renderSignalSourceDetail = (sourceDefinition: SourceDefinition, source: SignalSource | null) => {
    const featureValue =
      sourceDefinition.featureKey && dashboard.signals ? dashboard.signals.features[sourceDefinition.featureKey] : null;

    return (
      <>
        <header className="detail-hero">
          <div>
            <p className="eyebrow">Source Detail</p>
            <h1>{sourceDefinition.name}</h1>
            <p className="hero__subtitle">{sourceDefinition.detail}</p>
          </div>
          <div className="hero__actions">
            <button className="button button--secondary" onClick={() => navigate({ page: 'dashboard' })}>
              Back to Dashboard
            </button>
            <button
              className="button"
              onClick={() => void handleSourceDetailRefresh(sourceDefinition.name)}
              disabled={refreshingSourceName === sourceDefinition.name}
            >
              {refreshingSourceName === sourceDefinition.name ? 'Refreshing...' : 'Refresh Source'}
            </button>
          </div>
        </header>

        {error ? (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        ) : null}

        {sourceDefinition.id === 'opensky-network' && openSkyError ? (
          <div className="notice notice--error" role="alert">
            {openSkyError}
          </div>
        ) : null}

        {actionMessage ? <div className="notice notice--success">{actionMessage}</div> : null}

        <section className="metric-grid" aria-label={`${sourceDefinition.name} detail`}>
          <MetricCard
            label="Status"
            value={source ? titleCase(source.status) : 'Unknown'}
            detail={source ? `Mode ${formatSourceMode(source.mode)}` : 'Awaiting source snapshot'}
            accent={
              source ? <StatusBadge tone={getSourceTone(source.status)}>{titleCase(source.status)}</StatusBadge> : undefined
            }
          />
          <MetricCard
            label="Signal Feature"
            value={featureValue === null ? 'Unavailable' : formatPercent(featureValue)}
            detail={sourceDefinition.featureKey ? labelizeFeature(sourceDefinition.featureKey) : 'No mapped feature'}
            action={
              sourceDefinition.id === 'notam-feed' ? (
                <button
                  className="icon-help-button"
                  onClick={() => setFeatureLogicSourceId('notam-feed')}
                  aria-label="Open NOTAM signal feature logic"
                  title="NOTAM Signal Feature Logic"
                >
                  ?
                </button>
              ) : sourceDefinition.id === 'opensky-network' ? (
                <button
                  className="icon-help-button"
                  onClick={() => setFeatureLogicSourceId('opensky-network')}
                  aria-label="Open flight anomaly logic"
                  title="Flight Anomaly Logic"
                >
                  ?
                </button>
              ) : undefined
            }
          />
          <MetricCard
            label="Last Checked"
            value={source ? formatDateTime(source.last_checked_at) : 'Unavailable'}
            detail="Latest collector observation"
          />
          <MetricCard
            label="Suspicious Region"
            value={dashboard.signals?.region_focus ?? 'Unknown'}
            detail={`Snapshot captured ${formatDateTime(dashboard.signals?.generated_at)}`}
          />
        </section>

        <div className="dashboard-grid dashboard-grid--detail">
          <SectionCard title="Source Summary" subtitle="Current source role in the normalized model">
            <div className="detail-stack">
              <p>{sourceDefinition.summary}</p>
              <p>{sourceDefinition.detail}</p>
            </div>
          </SectionCard>

          <SectionCard title="Model Context" subtitle="Current normalized features from the latest snapshot">
            <div className="feature-grid">
              {featureEntries.map(([feature, value]) => (
                <div
                  key={feature}
                  className={`feature-tile${feature === sourceDefinition.featureKey ? ' feature-tile--active' : ''}`}
                >
                  <span>{labelizeFeature(feature)}</span>
                  <strong>{formatPercent(value)}</strong>
                </div>
              ))}
            </div>
          </SectionCard>
        </div>
      </>
    );
  };

  const renderNotamSourceDetail = (sourceDefinition: SourceDefinition, source: SignalSource | null) => {
    const featureValue =
      (dashboard.signals ? dashboard.signals.features.notam_spike : null) ?? notamDetail?.notam_spike ?? null;
    const topClassifications = notamDetail?.classification_breakdown ?? [];
    const topLocations = notamDetail?.location_breakdown ?? [];
    const representativeNotices = notamDetail?.representative_notices ?? [];

    return (
      <>
        <header className="detail-hero">
          <div>
            <p className="eyebrow">Source Detail</p>
            <h1>{sourceDefinition.name}</h1>
            <p className="hero__subtitle">{sourceDefinition.detail}</p>
          </div>
          <div className="hero__actions">
            <button className="button button--secondary" onClick={() => navigate({ page: 'dashboard' })}>
              Back to Dashboard
            </button>
            <button
              className="button"
              onClick={() => void handleSourceDetailRefresh(sourceDefinition.name)}
              disabled={refreshingSourceName === sourceDefinition.name}
            >
              {refreshingSourceName === sourceDefinition.name ? 'Refreshing...' : 'Refresh Source'}
            </button>
          </div>
        </header>

        {error ? (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        ) : null}

        {notamError ? (
          <div className="notice notice--error" role="alert">
            {notamError}
          </div>
        ) : null}

        {actionMessage ? <div className="notice notice--success">{actionMessage}</div> : null}

        <section className="metric-grid" aria-label={`${sourceDefinition.name} detail`}>
          <MetricCard
            label="Status"
            value={source ? titleCase(source.status) : 'Unknown'}
            detail={source ? `Mode ${formatSourceMode(source.mode)}` : 'Awaiting source snapshot'}
            accent={
              source ? <StatusBadge tone={getSourceTone(source.status)}>{titleCase(source.status)}</StatusBadge> : undefined
            }
          />
          <MetricCard
            label="Signal Feature"
            value={featureValue === null ? 'Unavailable' : formatPercent(featureValue)}
            detail={
              notamDetail
                ? `${notamDetail.alert_notice_count} alert-weighted and ${notamDetail.restricted_notice_count} restricted notices are currently contributing.`
                : 'Normalized NOTAM spike from the latest stored notice set.'
            }
            action={
              <button
                className="icon-help-button"
                onClick={() => setFeatureLogicSourceId('notam-feed')}
                aria-label="Open NOTAM signal feature logic"
                title="NOTAM Signal Feature Logic"
              >
                ?
              </button>
            }
          />
          <MetricCard
            label="Current Notices"
            value={notamDetail ? `${notamDetail.notice_count}` : 'Unavailable'}
            detail={
              notamDetail
                ? `${notamDetail.alert_notice_count} alert-flagged, ${notamDetail.restricted_notice_count} restricted-language notices`
                : 'Loading latest NOTAM count'
            }
          />
          <MetricCard
            label="Effective Window"
            value={
              notamDetail?.effective_window_end
                ? formatDateTime(notamDetail.effective_window_end)
                : 'Unavailable'
            }
            detail={
              notamDetail
                ? formatNotamWindow(notamDetail.effective_window_start, notamDetail.effective_window_end)
                : `Snapshot captured ${formatDateTime(dashboard.signals?.generated_at)}`
            }
          />
        </section>

        <div className="dashboard-grid dashboard-grid--detail">
          <SectionCard title="Operational Summary" subtitle={`Latest stored NOTAM observation ${formatDateTime(notamDetail?.generated_at ?? source?.last_checked_at)}`}>
            {!notamDetail ? (
              <p className="empty-state">Loading current NOTAM detail...</p>
            ) : (
              <div className="detail-stack">
                <p>{notamDetail.summary}</p>
                <p>Production refresh currently runs checklist-first to stay inside the FAA API request budget.</p>
                <p>
                  Latest upstream update:{' '}
                  {notamDetail.latest_updated_at ? formatDateTime(notamDetail.latest_updated_at) : 'Unavailable'}
                </p>
                {notamDetail.collector_fallback_reason ? (
                  <p>Collector fallback: {notamDetail.collector_fallback_reason}</p>
                ) : null}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Classification Breakdown" subtitle="Current NOTAM mix by classification">
            {!notamDetail ? (
              <p className="empty-state">Loading classification distribution...</p>
            ) : topClassifications.length === 0 ? (
              <p className="empty-state">No classification breakdown is available for the current snapshot.</p>
            ) : (
              <div className="feature-grid">
                {topClassifications.map((item) => (
                  <div key={item.label} className="feature-tile feature-tile--active">
                    <span>{item.label}</span>
                    <strong>{item.count}</strong>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Top Locations" subtitle="Highest-volume locations in the current feed">
            {!notamDetail ? (
              <p className="empty-state">Loading location concentration...</p>
            ) : topLocations.length === 0 ? (
              <p className="empty-state">No location concentration is available for the current snapshot.</p>
            ) : (
              <div className="feature-grid">
                {topLocations.map((item) => (
                  <div key={item.label} className="feature-tile">
                    <span>{item.label}</span>
                    <strong>{item.count}</strong>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Representative Notices" subtitle="Sample notices from the live NOTAM set">
            {!notamDetail ? (
              <p className="empty-state">Loading representative notices...</p>
            ) : representativeNotices.length === 0 ? (
              <p className="empty-state">No representative notices are available for the current snapshot.</p>
            ) : (
              <div className="notam-notice-list">
                {representativeNotices.map((notice) => (
                  <article key={notice.notice_id} className="notam-notice-card">
                    <div className="notam-notice-card__header">
                      <div>
                        <strong>{notice.notice_id}</strong>
                        <p>{notice.location ?? 'Unknown location'}{notice.classification ? ` · ${notice.classification}` : ''}</p>
                      </div>
                      <div className="notam-notice-card__flags">
                        {notice.is_alert ? <StatusBadge tone="warning">Alert-weighted</StatusBadge> : null}
                        {notice.is_restricted ? <StatusBadge tone="danger">Restricted</StatusBadge> : null}
                      </div>
                    </div>
                    <p>{notice.text}</p>
                    <p className="notam-notice-card__window">
                      {formatNotamWindow(notice.effective_start, notice.effective_end)}
                    </p>
                  </article>
                ))}
              </div>
            )}
          </SectionCard>
        </div>
      </>
    );
  };

  const renderOpenSkySourceDetail = (sourceDefinition: SourceDefinition, source: SignalSource | null) => {
    const openSkySignalAssessment: OpenSkySignalAssessment | null = openSkyAnomalies?.assessment ?? null;
    const featureValue =
      (typeof openSkySignalAssessment?.probability_percent === 'number'
        ? openSkySignalAssessment.probability_percent / 100
        : null) ??
      (sourceDefinition.featureKey && dashboard.signals ? dashboard.signals.features[sourceDefinition.featureKey] : null) ??
      openSkyAnomalies?.flight_anomaly ??
      null;
    const openSkyFilteredAnomalies = openSkyAnomalies
      ? openSkyAnomalies.anomalies.filter(
          (anomaly) => openSkyReasonFilter === 'all' || anomaly.reasons.includes(openSkyReasonFilter),
        )
      : [];
    const openSkyMapAnomalies = openSkyFilteredAnomalies.filter((anomaly) =>
      hasCoordinates(anomaly.latitude, anomaly.longitude),
    );

    return (
      <>
        <header className="detail-hero">
          <div>
            <p className="eyebrow">Source Detail</p>
            <h1>{sourceDefinition.name}</h1>
            <p className="hero__subtitle">{sourceDefinition.detail}</p>
          </div>
          <div className="hero__actions">
            <button className="button button--secondary" onClick={() => navigate({ page: 'dashboard' })}>
              Back to Dashboard
            </button>
            <button
              className="button"
              onClick={() => void handleSourceDetailRefresh(sourceDefinition.name)}
              disabled={refreshingSourceName === sourceDefinition.name || isRefreshingOpenSkySignal}
            >
              {refreshingSourceName === sourceDefinition.name ? 'Refreshing...' : 'Refresh Source'}
            </button>
            <button
              className="button button--secondary"
              onClick={() => void handleRefreshOpenSkySignal()}
              disabled={isRefreshingOpenSkySignal || refreshingSourceName === sourceDefinition.name}
            >
              {isRefreshingOpenSkySignal ? 'Refreshing Signal...' : 'Refresh Signal'}
            </button>
          </div>
        </header>

        {error ? (
          <div className="notice notice--error" role="alert">
            {error}
          </div>
        ) : null}

        {openSkyError ? (
          <div className="notice notice--error" role="alert">
            {openSkyError}
          </div>
        ) : null}

        {actionMessage ? <div className="notice notice--success">{actionMessage}</div> : null}

        <section className="metric-grid" aria-label={`${sourceDefinition.name} detail`}>
          <MetricCard
            label="Status"
            value={source ? titleCase(source.status) : 'Unknown'}
            detail={source ? `Mode ${formatSourceMode(source.mode)}` : 'Awaiting source snapshot'}
            accent={
              source ? <StatusBadge tone={getSourceTone(source.status)}>{titleCase(source.status)}</StatusBadge> : undefined
            }
          />
          <MetricCard
            label="Signal Feature"
              value={featureValue === null ? 'Unavailable' : formatPercent(featureValue)}
              detail={
                typeof openSkySignalAssessment?.probability_percent === 'number'
                  ? 'Current AI probability returned by Refresh Signal.'
                  : !dashboard.signals
                    ? sourceDefinition.featureKey
                      ? labelizeFeature(sourceDefinition.featureKey)
                      : 'No mapped feature'
                    : !openSkyAnomalies
                      ? 'Persisted snapshot value used for risk scoring. Loading current anomaly snapshot.'
                      : openSkyAnomalies.anomalies.length === 0
                        ? 'Persisted snapshot value used for risk scoring. No current anomaly triggers in the latest OpenSky snapshot.'
                        : `Persisted snapshot value used for risk scoring. ${openSkyAnomalies.anomalies.length} flagged flights in the latest snapshot.`
              }
            action={
              <button
                className="icon-help-button"
                onClick={() => setFeatureLogicSourceId('opensky-network')}
                aria-label="Open flight anomaly logic"
                title="Flight Anomaly Logic"
              >
                ?
              </button>
            }
          />
          <MetricCard
            label="Last Checked"
            value={source ? formatDateTime(source.last_checked_at) : 'Unavailable'}
            detail="Latest collector observation"
          />
          <MetricCard
            label="Suspicious Region"
            value={dashboard.signals?.region_focus ?? 'Unknown'}
            detail={`Snapshot captured ${formatDateTime(dashboard.signals?.generated_at)}`}
          />
        </section>

        <div className="dashboard-grid dashboard-grid--detail dashboard-grid--detail-opensky">
          <SectionCard
            title="Flight Filters"
            subtitle={`Refine the anomaly view ${formatDateTime(openSkyAnomalies?.generated_at ?? source?.last_checked_at)}`}
          >
            {!openSkyAnomalies ? (
              <p className="empty-state">Loading current suspicious flights...</p>
            ) : openSkyAnomalies.anomalies.length === 0 ? (
              <p className="empty-state">No suspicious flights are currently flagged by the OpenSky anomaly rules.</p>
            ) : (
              <>
                <div className="detail-stack">
                  <p>Flagged flights: {openSkyAnomalies.anomalies.length}</p>
                  <p>
                    Active filter: {openSkyReasonFilter === 'all' ? 'All reasons' : formatOpenSkyReason(openSkyReasonFilter)}
                  </p>
                </div>
                <div className="anomaly-filter-bar" aria-label="Filter anomalies by reason">
                  <button
                    className={`filter-chip${openSkyReasonFilter === 'all' ? ' filter-chip--active' : ''}`}
                    onClick={() => setOpenSkyReasonFilter('all')}
                  >
                    All reasons
                  </button>
                  {openSkyReasonOptions.map((reason) => (
                    <button
                      key={reason}
                      className={`filter-chip${openSkyReasonFilter === reason ? ' filter-chip--active' : ''}`}
                      onClick={() => setOpenSkyReasonFilter(reason)}
                    >
                      {formatOpenSkyReason(reason)}
                    </button>
                  ))}
                </div>
              </>
            )}
          </SectionCard>

          <div className="opensky-main-column">
            <SectionCard
              title="AI Signal Assessment"
              subtitle={`Latest AI signal pass ${formatDateTime(dashboard.signals?.generated_at ?? source?.last_checked_at)}`}
            >
              <div className="opensky-assessment-card">
                <div className="opensky-assessment-card__hero">
                  <div>
                    <p className="opensky-assessment-card__eyebrow">Suspicious Region</p>
                    <h3>{dashboard.signals?.region_focus ?? 'Unknown'}</h3>
                  </div>
                  <div className="opensky-assessment-card__metric">
                    <span>Last Checked</span>
                    <strong>{source ? formatDateTime(source.last_checked_at) : 'Unavailable'}</strong>
                  </div>
                </div>
                {openSkySignalAssessment ? (
                  <div className="detail-stack">
                    <p>Status: {openSkySignalAssessment.status ? titleCase(openSkySignalAssessment.status) : 'Unavailable'}</p>
                    <p>
                      Probability:{' '}
                      {typeof openSkySignalAssessment.probability_percent === 'number'
                        ? formatPercent(openSkySignalAssessment.probability_percent / 100)
                        : 'Unavailable'}
                    </p>
                    <p>
                      Countries:{' '}
                      {openSkySignalAssessment.countries.length > 0
                        ? openSkySignalAssessment.countries.join(', ')
                        : 'Unavailable'}
                    </p>
                    <p>Explanation: {openSkySignalAssessment.explanation ?? 'Unavailable'}</p>
                    <p>Prompt version: {openSkySignalAssessment.prompt_version}</p>
                  </div>
                ) : (
                  <p className="empty-state">No AI signal assessment is available for the current anomaly snapshot.</p>
                )}
              </div>
            </SectionCard>

            <SectionCard
              title="Flight Anomaly Map"
              subtitle={
                selectedOpenSkyAnomaly && hasCoordinates(selectedOpenSkyAnomaly.latitude, selectedOpenSkyAnomaly.longitude)
                  ? `Focused on ${selectedOpenSkyAnomaly.icao24} at ${selectedOpenSkyAnomaly.latitude!.toFixed(2)}, ${selectedOpenSkyAnomaly.longitude!.toFixed(2)}`
                  : 'Select a flagged flight to focus the map'
              }
            >
              {!openSkyAnomalies ? (
                <p className="empty-state">Loading anomaly positions...</p>
              ) : (
                <div className="anomaly-map">
                  <OpenSkyMap
                    anomalies={openSkyMapAnomalies}
                    selectedAnomalyId={selectedOpenSkyAnomalyId}
                    onSelectAnomaly={setSelectedOpenSkyAnomalyId}
                  />
                  <div className="anomaly-map__legend">
                    <span className="anomaly-map__legend-item">
                      <span className="anomaly-map__legend-swatch anomaly-map__legend-swatch--flight" aria-hidden="true" />
                      Flagged flights
                    </span>
                    <span className="anomaly-map__legend-item">
                      <span className="anomaly-map__legend-swatch anomaly-map__legend-swatch--base" aria-hidden="true" />
                      US/NATO airfields
                    </span>
                    <span>Callsign is the flight label; ICAO24 is the transponder hex identifier.</span>
                  </div>
                  {openSkyMapAnomalies.length === 0 ? (
                    <p className="empty-state">No anomaly positions are available right now. Base locations remain visible for context.</p>
                  ) : null}
                </div>
              )}
            </SectionCard>

            <SectionCard
              title="Flagged Flights"
              subtitle={`Filtered anomaly list ${formatDateTime(openSkyAnomalies?.generated_at ?? source?.last_checked_at)}`}
            >
              {!openSkyAnomalies ? (
                <p className="empty-state">Loading current suspicious flights...</p>
              ) : openSkyFilteredAnomalies.length === 0 ? (
                <p className="empty-state">No anomalies match the selected reason filter.</p>
              ) : (
                <div className="anomaly-list">
                  {openSkyFilteredAnomalies.map((anomaly) => (
                    <article
                      key={anomaly.icao24}
                      className={`anomaly-row${selectedOpenSkyAnomalyId === anomaly.icao24 ? ' anomaly-row--selected' : ''}`}
                    >
                      <button
                        className="anomaly-row__select"
                        onClick={() => setSelectedOpenSkyAnomalyId(anomaly.icao24)}
                        aria-label={`Focus anomaly ${anomaly.callsign ?? anomaly.icao24}`}
                      >
                        <strong>{anomaly.callsign ?? 'Unknown callsign'}</strong>
                        <span>{anomaly.origin_country ?? 'Unknown origin'} · ICAO24 {anomaly.icao24}</span>
                      </button>
                      <button
                        className="icon-detail-button"
                        onClick={() => setOpenSkyDetailAnomalyId(anomaly.icao24)}
                        aria-label={`Open anomaly detail ${anomaly.callsign ?? anomaly.icao24}`}
                        title={`Open anomaly detail for ${anomaly.callsign ?? anomaly.icao24}`}
                      >
                        🔎
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </SectionCard>
          </div>
        </div>
      </>
    );
  };

  const renderSourceDetail = () => {
    if (!currentSourceDefinition) {
      return renderDashboard();
    }

    if (currentSourceDefinition.id === 'gdelt') {
      return renderGdeltDetail(currentSourceDefinition, currentSignalSource);
    }

    if (currentSourceDefinition.id === 'notam-feed') {
      return renderNotamSourceDetail(currentSourceDefinition, currentSignalSource);
    }

    if (currentSourceDefinition.hasDedicatedDetailData) {
      return renderPizzaIndexDetail(currentSourceDefinition);
    }

    if (currentSourceDefinition.id === 'opensky-network') {
      return renderOpenSkySourceDetail(currentSourceDefinition, currentSignalSource);
    }

    return renderSignalSourceDetail(currentSourceDefinition, currentSignalSource);
  };

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <p className="eyebrow">Predict Strike</p>
          <h2>Operator Console</h2>
        </div>

        <nav className="sidebar__nav" aria-label="Primary navigation">
          <button
            className={`sidebar__link${route.page === 'dashboard' ? ' sidebar__link--active' : ''}`}
            onClick={() => navigate({ page: 'dashboard' })}
          >
            Dashboard
          </button>

          <div className="sidebar__group">
            <p className="sidebar__group-label">Sources</p>
            {SOURCE_DEFINITIONS.map((source) => (
              <button
                key={source.id}
                className={`sidebar__sublink${route.page === 'source' && route.sourceId === source.id ? ' sidebar__sublink--active' : ''}`}
                onClick={() => navigate({ page: 'source', sourceId: source.id })}
              >
                {source.name}
              </button>
            ))}
          </div>
        </nav>
      </aside>

      <main className="app-shell">{route.page === 'dashboard' ? renderDashboard() : renderSourceDetail()}</main>
      {renderFeatureLogicModal()}
      {route.page === 'source' && route.sourceId === 'opensky-network' && openSkyDetailAnomaly ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setOpenSkyDetailAnomalyId(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="opensky-anomaly-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal__header">
              <div>
                <p className="eyebrow">Flight Detail</p>
                <h2 id="opensky-anomaly-title">{openSkyDetailAnomaly.callsign ?? openSkyDetailAnomaly.icao24}</h2>
              </div>
              <button className="button button--secondary button--inline" onClick={() => setOpenSkyDetailAnomalyId(null)}>
                Close
              </button>
            </div>
            <div className="detail-stack">
              <p>Callsign: {openSkyDetailAnomaly.callsign ?? 'Unavailable'}</p>
              <p>ICAO24: {openSkyDetailAnomaly.icao24}</p>
              <p>Country: {openSkyDetailAnomaly.origin_country ?? 'Unknown origin'}</p>
              <p>Velocity: {openSkyDetailAnomaly.velocity ? `${Math.round(openSkyDetailAnomaly.velocity)} m/s` : 'n/a'}</p>
              <p>
                Barometric altitude:{' '}
                {openSkyDetailAnomaly.baro_altitude ? `${Math.round(openSkyDetailAnomaly.baro_altitude)} m` : 'n/a'}
              </p>
              <p>
                Geometric altitude:{' '}
                {openSkyDetailAnomaly.geo_altitude ? `${Math.round(openSkyDetailAnomaly.geo_altitude)} m` : 'n/a'}
              </p>
              <p>
                Position: {openSkyDetailAnomaly.latitude?.toFixed(2) ?? 'n/a'},{' '}
                {openSkyDetailAnomaly.longitude?.toFixed(2) ?? 'n/a'}
              </p>
              <div className="anomaly-detail__reasons">
                {openSkyDetailAnomaly.reasons.map((reason) => (
                  <StatusBadge key={reason} tone="warning">
                    {formatOpenSkyReason(reason)}
                  </StatusBadge>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
