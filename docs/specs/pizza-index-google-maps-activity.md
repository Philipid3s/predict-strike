# Pizza Index Google Maps Activity Spec

This document defines the design for the **Google Maps restaurant activity**
slice that feeds Predict Strike's `pizza_index`.

The core Pizza Index contract is now implemented in the live API and documented
in `docs/api/openapi.yml`. This spec remains the higher-level design reference
for provider behavior, scoring logic, and future enhancements.

The temporary `Behavioral Signals` placeholder has been replaced in the live
signal-source inventory by the Pizza Index collector/source label.

## 1. Objective

Build a resilient collection path for restaurant activity near strategic U.S.
government and defense locations so Predict Strike can derive a `pizza_index`
from **current busyness relative to normal patterns**.

The required signal is:

- how busy the monitored restaurant is **now**
- how busy it is **usually** at the same time window
- the delta between those two values

Generic search-result metadata such as rating or address is useful context, but
it is secondary to busyness.

## 2. Scope Boundary

This slice is a **behavioral intelligence** source.

It is **not** part of:

- `GDELT`
- Google News
- narrative/news intensity monitoring

It is a separate collector family whose output is intended to feed only:

- `pizza_index`
- later behavioral corroboration workflows

It is also the planned replacement for the temporary `Behavioral Signals`
placeholder currently used in the live signal-source inventory.

## 3. Primary Design Principles

1. Busyness is the primary signal.
2. Preserve the exact Google Maps place URLs for monitored targets even if the
   primary provider is not Google Maps directly.
3. The primary upstream must expose current/usual activity or enough structure
   to derive it honestly.
4. Use a provider abstraction so PizzINT and SerpApi can be swapped or
   extended without changing downstream scoring.
6. Distinguish **full**, **partial**, and **unavailable** data quality so weak
   observations do not masquerade as strong signal input.

## 4. Collection Architecture

```text
Target Registry
   ->
Pizza Activity Collector
   ->
Provider Layer
   -> PizzINT dashboard JSON (primary)
   -> SerpApi (fallback)
   ->
Normalization
   ->
Observation Store
   ->
Pizza Index Scoring
   ->
Signal Snapshot
```

### Provider intent

- **PizzINT dashboard JSON** is the primary path
- **SerpApi** is the reliability fallback
- **Cache** should sit in front of repeated place requests
- the registry must keep the exact upstream Google Maps place URLs so fallback
  and auditability still point at the intended monitored places

## 5. Target Registry

The collector should operate against a **fixed monitored target registry**
rather than generic ad hoc search queries.

Initial Pentagon-area targets:

- Domino's Pizza - Pentagon City
- Papa Johns Pizza - Pentagon City
- We The Pizza - Pentagon Row
- Extreme Pizza - Pentagon Row
- Wiseguy Pizza - Rosslyn
- District Taco - Pentagon City
- McDonald's - Pentagon City
- Chipotle - Pentagon City

The current implementation monitors the first five pizza-focused targets. The
additional food-traffic targets remain planned extensions.

Each target record should include:

- `target_id`
- `display_name`
- `category`
- `priority_weight`
- `location_cluster`
- `google_maps_url`
- optional `place_hint`
- `active`

### Why a target registry is required

- the Pizza Index is based on repeated monitoring of the **same places**
- place-to-place baselines are more meaningful than one-off searches
- direct place targeting reduces ambiguity compared with broad `pizza near X`
  searches

## 6. Proposed Endpoints

These are planned endpoints for implementation planning only.

### A. List monitored targets

```text
GET /api/v1/pizza-index/targets
```

Purpose:

- return the configured monitored places
- support operator visibility and future target management

### B. Collect a single target activity snapshot

```text
GET /api/v1/pizza-index/targets/{target_id}/activity
```

Purpose:

- fetch the latest normalized activity observation for one target
- expose provider source, data quality, and busyness fields

### C. Force refresh across all active targets

```text
POST /api/v1/pizza-index/refresh
```

Purpose:

- run a fresh collection pass across the full monitored registry
- persist raw observations and derived aggregate output

### D. Get latest aggregate Pizza Index snapshot

```text
GET /api/v1/pizza-index/latest
```

Purpose:

- return the latest derived `pizza_index`
- expose per-target contributions and confidence

### Optional internal-only endpoint

```text
GET /internal/maps/places/activity?target_id={target_id}
```

Purpose:

- isolate provider orchestration from the external analyst-facing API
- useful if Puppeteer runs in a dedicated worker/service

## 7. Normalized Schemas

### A. Target descriptor

```json
{
  "target_id": "dominos_pentagon_city",
  "display_name": "Domino's Pizza - Pentagon City",
  "category": "pizza",
  "priority_weight": 1.0,
  "location_cluster": "pentagon",
  "google_maps_url": "https://www.google.com/maps/place/...",
  "active": true
}
```

### B. Target activity observation

```json
{
  "target_id": "dominos_pentagon_city",
  "display_name": "Domino's Pizza - Pentagon City",
  "provider": "pizzint",
  "provider_mode": "primary",
  "collected_at": "2026-03-07T13:40:00Z",
  "data_quality": "full",
  "capture_status": "pizzint_dashboard_ok",
  "is_open": true,
  "current_busyness_percent": 82,
  "usual_busyness_percent": 46,
  "busyness_delta_percent": 36,
  "current_busyness_label": "busier_than_usual",
  "rating": null,
  "reviews_count": null,
  "address": null,
  "google_maps_url": "https://www.google.com/maps/place/..."
}
```

### C. Aggregate Pizza Index snapshot

```json
{
  "generated_at": "2026-03-07T13:40:30Z",
  "pizza_index": 0.71,
  "pizza_index_confidence": 0.78,
  "quality_summary": {
    "full_count": 4,
    "partial_count": 2,
    "unavailable_count": 2
  },
  "targets": [
    {
      "target_id": "dominos_pentagon_city",
      "target_score": 0.84,
      "weight": 1.0,
      "data_quality": "full",
      "provider": "pizzint"
    }
  ]
}
```

## 8. Required Activity Fields

The following fields are required for **full-quality** scoring:

- `current_busyness_percent`
- `usual_busyness_percent`
- `busyness_delta_percent`
- `is_open`

The following fields are supporting context:

- `display_name`
- `address`
- `rating`
- `reviews_count`
- `google_maps_url`
- `capture_status`

### Upstream limitation

If the primary upstream does not expose a usable current/usual activity signal
for a monitored place, the system must fall back honestly instead of treating
the Google Maps link alone as a usable busyness observation.

## 9. Data Quality Model

### `full`

Use when:

- the place match is confident
- current busyness is present
- usual busyness is present
- the delta can be computed directly

### `partial`

Use when:

- the place match is confident
- some secondary metadata is present
- but one or more required busyness fields are missing

Examples:

- current busyness missing
- usual busyness missing
- SerpApi returns place metadata but not equivalent activity fields
- the primary upstream exposes only the Google Maps link for a target without a
  usable activity value

### `unavailable`

Use when:

- the provider cannot retrieve the place
- captcha or bot detection blocks access
- repeated attempts fail
- the result cannot be trusted or normalized

## 10. Provider and Fallback Behavior

### Primary path

1. load the target from the registry
2. fetch the PizzINT dashboard payload
3. select the configured monitored place from the upstream payload
4. normalize current activity, usual baseline, closed/open state, and preserved
   Google Maps URL
5. if busyness is available, normalize and return

### Fallback conditions

Fallback to SerpApi when:

- timeout occurs
- the primary upstream fails
- the configured target is missing from the upstream payload
- the provider returns empty results

### Full versus partial fallback

SerpApi is a **full fallback** only if it returns equivalent activity fields
needed to compute:

- `current_busyness_percent`
- `usual_busyness_percent`
- `busyness_delta_percent`

If SerpApi returns only place metadata, the observation must be marked:

- `data_quality = partial`

It must not be treated as a full substitute for the primary upstream.

## 11. Cache and Retry Policy

Recommended initial defaults:

- cache TTL: 10 minutes
- PizzINT fetch timeout: 8 seconds
- fallback call: 1 SerpApi attempt
- SerpApi daily fallback budget: 4 calls per day by default

Rationale:

- activity changes matter, but minute-by-minute collection is not necessary for
  the first implementation
- the signal is stronger when sampled repeatedly and compared against historical
  norms, not when every page view triggers a fresh scrape

## 12. Pizza Index Scoring

The scoring model should remain transparent and conservative.

### Per-target delta normalization

For each target:

```text
raw_delta = current_busyness_percent - usual_busyness_percent
normalized_delta = clamp(raw_delta / 50, 0, 1)
```

This means:

- no uplift if the place is at or below usual levels
- full contribution if it is far above baseline

### Data-quality weight

```text
full = 1.0
partial = 0.4
unavailable = 0.0
```

### Open-state factor

```text
open = 1.0
unknown = 0.5
closed = 0.0
```

### Closed-state inference

If the primary payload clearly shows the place is closed and no live current
busyness value is exposed, the implementation may infer:

```text
current_busyness_percent = 0
current_busyness_label = "closed"
```

This is acceptable only when the closed state itself is directly observed from
the primary payload or an equivalent fallback payload.

### Per-target score

```text
target_score =
    normalized_delta
    * priority_weight
    * data_quality_weight
    * open_state_factor
```

### Aggregate Pizza Index

```text
pizza_index =
    clamp(sum(target_score) / sum(priority_weight for active targets), 0, 1)
```

### Confidence

```text
pizza_index_confidence =
    sum(priority_weight * data_quality_weight)
    / sum(priority_weight for active targets)
```

This keeps the signal interpretable:

- the score rises when monitored places are busier than normal
- confidence falls when the collection layer returns only partial or missing
  data

## 13. Implementation Milestones

### Milestone 1: Target registry and schema

- define monitored targets
- define normalized observation schema
- define data-quality states

### Milestone 2: Primary upstream provider

- upstream dashboard fetch
- target matching
- busyness normalization into the activity schema

### Milestone 3: SerpApi fallback

- fallback orchestration
- full versus partial quality classification
- provider error handling

### Milestone 4: Persistence and cache

- store raw provider payloads
- store normalized per-target observations
- cache recent observations

Status: implemented in the current backend.

### Milestone 5: Aggregate scoring

- compute per-target scores
- compute `pizza_index`
- compute confidence and quality summary

Status: implemented in the current backend.

### Milestone 6: Dashboard and alert integration

- expose latest Pizza Index snapshot
- show per-target activity cards
- allow the signal to contribute to broader risk scoring

## 14. Risks and Watch Points

- the PizzINT upstream is a third-party derived service
- upstream target coverage may not match every planned Predict Strike target
- upstream payload shape may change without notice
- SerpApi may not provide equivalent busyness fields for a true full fallback
- behavioral signals are inherently weaker than hard operational signals and
  should remain low-confidence without corroboration

## 15. Recommended Implementation Posture

For the first implementation pass:

- prioritize **targeted place monitoring** over generic search
- optimize for **busyness extraction**, not search breadth
- preserve raw observations for later backtesting and auditability
- treat partial data honestly rather than over-scoring weak signals
- keep this slice modular so it can later incorporate delivery apps, Trends, or
  other corroborating behavioral sources
