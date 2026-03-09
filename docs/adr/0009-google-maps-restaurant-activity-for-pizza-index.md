# ADR 0009: Google Maps Restaurant Activity as a Separate Pizza Index Slice

## Status
Accepted

## Date
2026-03-07

## Context
Predict Strike currently treats `pizza_index` as a soft behavioral signal, but
the underlying collection design had not been specified in a way that matches
the actual signal need.

The key signal is not generic Google Maps search metadata. The key signal is
**restaurant activity at specific monitored locations**, especially current
busyness versus the usual baseline for the same time window.

This design question also affects source boundaries. `GDELT` is a news and
narrative source. Google Maps restaurant activity is a different behavioral
collection slice and should not be modeled as part of GDELT/news monitoring.

The collection path is also operationally sensitive:

- Google Maps search results alone may not expose the required activity fields
- place-detail scraping is likely required to extract busyness/popular-times
  style data
- a third-party dashboard may expose already-normalized place activity and
  stable Google Maps target links
- SerpApi is more reliable as a fallback, but may not expose equivalent
  activity fields in every response shape

## Decision
Predict Strike will treat Google Maps restaurant activity as a **separate
behavioral-signal slice** that feeds `pizza_index`.

The design decisions are:

- `pizza_index` is sourced from Google Maps restaurant-activity collection,
  not from GDELT/news
- the temporary `Behavioral Signals` source label is a placeholder and should
  be replaced by Pizza Index once the backend Pizza Index contract exists
- the primary collection target is **current busyness versus usual busyness**
  for specific monitored places
- the collection model will use a **provider abstraction** with:
  - `pizzint` dashboard JSON as the primary provider
  - `serpapi` as the fallback provider
- the implemented primary path calls `https://www.pizzint.watch/api/dashboard-data`
  and normalizes the monitored target entries into Predict Strike's Pizza Index
  schema
- the target registry must preserve the upstream Google Maps place URLs so
  fallback lookup and auditability still point at exact monitored places
- SerpApi counts as a **full fallback** only when it returns equivalent activity
  fields required to compute the score
- when fallback returns only secondary metadata and not equivalent busyness
  fields, the observation is `partial_data`, not a full substitute
- SerpApi fallback usage must be quota-controlled because the available plan is
  constrained; the initial live implementation uses a configurable daily limit
  with a default of 4 fallback calls per day
- raw provider payloads should be persisted alongside normalized activity
  snapshots so smoke-test results and later backtesting can inspect exactly what
  the browser or fallback provider returned
- endpoints and schemas for this slice are documented in the live OpenAPI
  contract and the dedicated planning spec

## Consequences
- The project gains a clear separation between news monitoring and behavioral
  restaurant-activity monitoring.
- `pizza_index` planning can focus on target places, activity normalization,
  and data quality rather than generic search APIs.
- The current `Behavioral Signals` placeholder can be retired once the Pizza
  Index source and routes are scaffolded in the backend.
- Implementation requires a browser-automation worker/runtime rather than a
  simple REST collector only if direct Google Maps scraping is reintroduced.
- API planning must distinguish between:
  - place registry and target management
  - raw place-activity collection
  - derived pizza-index snapshots
- The live backend now persists normalized per-target activity plus raw provider
  payloads for Pizza Index observations.
- When the PizzINT payload marks a place closed and current activity is absent,
  the collector may infer `current_busyness_percent = 0` with
  `current_busyness_label = closed`.
- The live OpenAPI contract now distinguishes provider, provider mode, capture
  status, and data quality for Pizza Index observations.
