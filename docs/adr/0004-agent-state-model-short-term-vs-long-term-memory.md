# ADR 0004: Agent State Model (Short-Term vs Long-Term Memory)

## Status
Accepted

## Date
2026-03-03

## Context
The runtime contract defines task and tool interfaces, but the project also
needs a standard model for agent memory. Without a shared model,
implementations risk mixing ephemeral execution context with durable knowledge,
causing stale data, privacy risk, and inconsistent behavior across sessions.

## Decision
Adopt a two-layer state model with explicit promotion from short-term to
long-term.

1. Short-term memory (working state)
   - Scope: current task/session execution context only.
   - Storage: Redis or equivalent ephemeral store.
   - TTL: 6 to 24 hours.
   - Content: recent messages, tool outputs, plan checkpoints, retry state.

2. Long-term memory (durable state)
   - Scope: cross-session reusable knowledge.
   - Storage: PostgreSQL as default system of record.
   - Content types:
     - Episodic memory: outcomes and prior task events.
     - Semantic memory: stable facts and user/project preferences.

3. Promotion pipeline
   - Execute at task completion.
   - Promote only distilled facts with confidence and provenance metadata.
   - Enforce policy filters (PII classification, retention rules) before write.

Retrieval precedence:
- (1) short-term working state
- (2) recent episodic memory
- (3) semantic memory search

## Consequences
Positive:
- Predictable memory behavior and lower context pollution.
- Stronger safety and retention control over durable memory.
- Enables later vector indexing without changing logical memory model.

Trade-offs:
- Requires separate storage operational concerns (cache + database).
- Adds implementation complexity for promotion/deduplication logic.
