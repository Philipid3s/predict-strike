# ADR 0011: Dashboard Refresh Orchestration and SQLite History Policy

## Status
Accepted

## Date
2026-03-17

## Context
Predict Strike now has a defined operator-dashboard workflow across four active
source slices: `OpenSky Network`, `NOTAM Feed`, `GDELT`, and `Pizza Index
Activity`.

The product direction was still ambiguous in two areas:

- which actions a dashboard refresh button is supposed to orchestrate
- which outputs are cached in place versus persisted as historical records

That ambiguity is risky because the same words, such as "refresh source" and
"refresh signal", can mean different things at dashboard level versus source
detail level. It also creates storage drift: the repository already shows
partial SQLite persistence for source observations, signal snapshots, Pizza
Index caches, Polymarket observations, and alert history, but it did not yet
document a complete history policy for market opportunities and alert
evaluation runs.

## Decision
Predict Strike will treat dashboard refresh actions as orchestration commands
over append-only SQLite-backed historical snapshots.

### Dashboard orchestration rules

- The main dashboard `Refresh Signals` action must run both `Refresh Source`
  and `Refresh Signal` for each supported dashboard source in scope:
  `OpenSky Network`, `NOTAM Feed`, `GDELT`, and `Pizza Index Activity`.
- The main dashboard `Evaluate Alerts` action must first reload the latest
  relevant Polymarket opportunities using the current model percentage, then
  re-evaluate market edge and persist the resulting evaluation output.
- The dashboard pre-source status panel refresh control for a single source
  must run both `Refresh Source` and `Refresh Signal` for that source only.

### Source-detail rules

- On a source detail page, `Refresh source` means source collection only for
  that source page. It must fetch or reload upstream/source data and persist
  that load without implicitly recomputing the derived signal.
- On a source detail page, `Refresh signal` means signal recomputation only for
  that source page. It must recompute from the latest stored source data and
  persist a new derived snapshot without triggering a new upstream collection
  pass.

### SQLite history policy

- All loaded source data must be stored in SQLite as historical source-load
  records.
- All loaded Polymarket data must be stored in SQLite as historical
  market-load records.
- All signal computations must be stored in SQLite as historical derived
  signal snapshots.
- All market opportunity outputs and alert-evaluation outputs must be stored in
  SQLite as historical snapshots rather than overwritten cache rows.
- Analyst-facing alerts may still be materialized as alert records, but those
  alerts are downstream artifacts of a persisted evaluation run rather than the
  only retained audit trail.
- "Latest" API reads are projections over the newest persisted records, not a
  separate non-historical storage mode.

## Consequences
- Backend implementation should model dashboard refresh endpoints as
  orchestration flows, not as ambiguous single-step operations.
- Frontend copy and control placement should distinguish clearly between
  dashboard-level orchestration and source-detail single-purpose actions.
- OpenAPI descriptions and examples should describe refresh endpoints in terms
  of persisted historical snapshots and the current four-source dashboard
  scope.
- Existing partial persistence is directionally correct, but backend work still
  needs explicit historical storage for opportunity snapshots and
  evaluation-run snapshots if those tables are not already present.
