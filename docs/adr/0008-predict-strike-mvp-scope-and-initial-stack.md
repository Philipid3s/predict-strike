# ADR 0008: Predict Strike MVP Scope and Initial Implementation Stack

## Status
Accepted

## Date
2026-03-07

## Context
This repository is no longer a generic AI-agent system skeleton. It is being
bootstrapped into **Predict Strike**, an OSINT-driven prediction system for
monitoring geopolitical conflict signals and comparing internal risk estimates
with prediction-market pricing.

The project needs an explicit MVP scope and implementation stack before service
work begins. ADR 0005 requires stack choices to be documented rather than
emerging implicitly through implementation.

The initial product direction from kickoff planning includes:

- ingesting public-source signals related to air activity, maritime movement,
  NOTAM changes, news coverage, social OSINT, and soft behavioral indicators
- normalizing those signals into structured features
- computing an interpretable conflict risk score
- comparing that score against market prices from prediction venues such as
  Polymarket
- generating analyst-facing alerts before any automated execution is considered

## Decision
Predict Strike will begin with the following MVP boundaries and stack choices.

### MVP scope

The first implementation phase will prioritize:

- modular collectors for a limited set of public or documented sources
- a normalized feature store for conflict-signal snapshots
- a transparent weighted scoring model rather than a black-box model
- a market scanner that compares internal probabilities with current market
  pricing
- alert delivery and audit logging for analyst review

The MVP will defer:

- fully automated trade execution
- advanced satellite computer-vision pipelines
- broad social-platform scraping beyond narrowly approved sources
- complex model optimization beyond manually configured weights and later
  backtesting

### Initial stack

- **Primary language:** Python
- **Collector runtime support:** Node.js is permitted for browser-automation
  collector workers that support Python-owned backend flows
- **API/backend framework:** FastAPI
- **Primary application database:** SQLite for local MVP storage
- **Cache and short-lived queue support:** Redis
- **Scheduled/background work:** Celery where queueing is needed, with cron
  acceptable for simple polling jobs during early development
- **Frontend:** React-based operator dashboard
- **Architecture style:** modular collectors + scoring pipeline + alerting
  service, while preserving the agent-runtime baseline documented in
  `docs/specs/technical/agent-runtime/`

### Delivery posture

- analyst-facing alerts are the default action for MVP outputs
- any future trade execution capability requires a separate approval-oriented
  decision and follow-up ADR
- data-source usage must remain compatible with each provider's terms,
  availability, and rate limits
- the first backend scaffold exposes `GET /health`,
  `GET /api/v1/signals/latest`, `POST /api/v1/signals/refresh`,
  `POST /api/v1/risk/score`, `GET /api/v1/markets/opportunities`,
  `GET /api/v1/alerts`, and `POST /api/v1/alerts/evaluate` as a narrow MVP
  contract for health, feature snapshots, refresh-driven collection,
  explainable scoring, market comparison, and analyst-facing alert history

## Consequences
- The project can start implementation with a shared default stack and MVP
  boundary.
- Docker, environment templates, and service scaffolding should align with
  Python/FastAPI, React, SQLite, and Redis, while optional Node.js/browser
  automation remains available only if a direct scraping fallback is reintroduced.
- API contracts can now be drafted around collectors, features, risk scores,
  markets, and alerts without assuming full automation.
- The temporary `Behavioral Signals` source placeholder is now superseded by
  the dedicated Pizza Index slice described in ADR 0009.
- Future changes to the storage layer, worker runtime, or execution policy
  should be recorded in additional ADRs rather than silently replacing this
  baseline.
