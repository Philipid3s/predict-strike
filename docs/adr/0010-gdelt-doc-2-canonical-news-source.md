# ADR 0010: GDELT DOC 2.0 as the Canonical News Source

## Status
Accepted

## Date
2026-03-10

## Context
Predict Strike already exposes a `GDELT` source in the signal snapshot and a
dedicated analyst-facing GDELT detail endpoint. However, the project had not
explicitly recorded which upstream should count as the canonical news source
for this slice.

That ambiguity is operationally expensive:

- a generic search API is not the same thing as a news-monitoring system
- search-result providers introduce ranking noise, higher marginal cost, and
  weaker contract stability for article retrieval
- the existing backend implementation used a configurable article-feed URL, but
  the intended product slice is specifically narrative monitoring via GDELT

The product direction is now explicit:

- official **GDELT DOC 2.0** is the canonical upstream for article discovery
  and news-volume monitoring
- Brave Search is **not** the canonical source for this slice
- generic search providers may still be considered later for enrichment or
  corroboration, but not as the primary `GDELT` implementation

## Decision
Predict Strike will treat **official GDELT DOC 2.0** as the canonical upstream
for the `GDELT` news-monitoring slice.

The design decisions are:

- the collector contract for the `GDELT` slice is based on GDELT DOC 2.0
  article-list style results
- the `GDELT` source remains a news and narrative-pressure input, not a search
  abstraction over multiple providers
- Brave Search is non-canonical for this slice and should not define the
  source contract, response semantics, or persistence model
- generic search APIs may be used only as optional enrichment or analyst
  corroboration layers in future work
- the backend may continue to use cached or bootstrap fallback data when the
  canonical GDELT DOC path is unavailable, but those fallbacks do not redefine
  the source contract
- the dedicated GDELT detail endpoint must document the analyst-facing derived
  fields built from the canonical GDELT DOC article set

## Consequences
- The project now has a clear answer for what `GDELT_SOURCE_URL` is supposed to
  represent: a GDELT DOC 2.0 query endpoint, not an arbitrary search or feed
  URL.
- Backend collector work should tighten normalization around GDELT DOC 2.0
  article fields and query semantics.
- OpenAPI and frontend work should treat the GDELT detail route as a stable
  analyst-facing contract derived from GDELT DOC observations.
- If Brave Search or any other web-search provider is introduced later, it
  should be modeled as a separate enrichment decision rather than silently
  replacing the canonical GDELT source.
