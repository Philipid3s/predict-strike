import type { FeatureVector } from './types/api';

export interface SourceDefinition {
  id: string;
  name: string;
  summary: string;
  detail: string;
  featureKey?: keyof FeatureVector;
  supportsDashboardRefresh: boolean;
  hasDedicatedDetailData?: boolean;
}

export const SOURCE_DEFINITIONS: SourceDefinition[] = [
  {
    id: 'opensky-network',
    name: 'OpenSky Network',
    summary: 'Aircraft state sampling and military-like flight anomaly scoring.',
    detail: 'Tracks elevated air activity and military-like callsigns to feed the flight anomaly feature.',
    featureKey: 'flight_anomaly',
    supportsDashboardRefresh: true,
  },
  {
    id: 'notam-feed',
    name: 'NOTAM Feed',
    summary: 'Airspace notices and restriction spike monitoring.',
    detail: 'Parses current NOTAM notices and scores military or restrictive language to feed the NOTAM spike feature.',
    featureKey: 'notam_spike',
    supportsDashboardRefresh: true,
  },
  {
    id: 'gdelt',
    name: 'GDELT',
    summary: 'Freshness-weighted media monitoring for US/NATO strike-indicative reporting.',
    detail: 'Builds a representative recent article set, then uses AI assessment to feed the GDELT strike signal feature.',
    featureKey: 'news_volume',
    supportsDashboardRefresh: true,
    hasDedicatedDetailData: true,
  },
  {
    id: 'pizza-index-activity',
    name: 'Pizza Index Activity',
    summary: 'Restaurant-activity monitoring around monitored Pentagon-area pizza targets.',
    detail: 'Aggregates live and fallback restaurant activity signals into a Pizza Index score with per-target provider provenance.',
    featureKey: 'pizza_index',
    supportsDashboardRefresh: true,
    hasDedicatedDetailData: true,
  },
];

export const SOURCE_BY_ID = Object.fromEntries(
  SOURCE_DEFINITIONS.map((source) => [source.id, source]),
) as Record<string, SourceDefinition>;

export const SOURCE_ID_BY_NAME = Object.fromEntries(
  SOURCE_DEFINITIONS.map((source) => [source.name, source.id]),
) as Record<string, string>;

