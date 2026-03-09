# Agent State Model

This specification defines how runtime state is separated into short-term and
long-term memory.

## Goals

- Keep in-flight execution context isolated from durable knowledge.
- Make memory retrieval deterministic and bounded by runtime budgets.
- Enforce retention, privacy, and deletion guarantees.

## Memory Layers

## 1) Short-Term Memory (Working State)

- Purpose: support one in-flight task/session.
- Scope key: `tenant_id + user_id + session_id` (or `task_id` for single-run tasks).
- Store: Redis (recommended), local cache for development only.
- TTL: default 12h, configurable within 6-24h.
- Durability: best-effort only; must not be used as source of truth.

Typical fields:
- recent conversation turns
- tool call snapshots
- current plan/checkpoint
- retry counters and deadlines

## 2) Long-Term Memory (Durable State)

- Purpose: reusable memory across sessions.
- Store: PostgreSQL (system of record), optional vector index as secondary index.
- Durability: required.
- Retention: policy-driven per memory item.

Memory types:
- `episodic`: task outcomes, observations, and event summaries.
- `semantic`: stable facts, preferences, and environment knowledge.

## Promotion Pipeline (Short-Term -> Long-Term)

Run after task completion or explicit checkpoint:

1. Extract candidate memory facts from working state.
2. Normalize and deduplicate.
3. Score confidence and attach provenance.
4. Apply policy checks (PII, tenancy, retention).
5. Persist accepted items to long-term memory.

Rejected candidates are dropped and should not be persisted.

## Retrieval Order

Runtime retrieval must be deterministic:

1. Load short-term working state for current scope.
2. Load recent episodic items (most recent first, bounded window).
3. Load semantic memory (query + optional vector similarity).
4. Merge by precedence and token budget.

If budget is exceeded, semantic retrieval is truncated first.

## Data Model (Minimum)

`memory_items`
- `id` (UUID, PK)
- `tenant_id` (TEXT, indexed)
- `user_id` (TEXT, indexed)
- `scope` (ENUM: `short_term`, `episodic`, `semantic`)
- `content` (JSONB)
- `confidence` (NUMERIC(3,2), nullable)
- `source_task_id` (UUID, nullable)
- `created_at` (TIMESTAMPTZ)
- `expires_at` (TIMESTAMPTZ, nullable)
- `pii_class` (ENUM: `none`, `sensitive`, `restricted`)
- `version` (INTEGER)

`memory_links`
- `id` (UUID, PK)
- `from_item_id` (UUID, FK -> `memory_items.id`)
- `to_item_id` (UUID, FK -> `memory_items.id`)
- `relation` (TEXT)

`memory_events`
- `event_id` (TEXT, PK)
- `operation` (ENUM: `insert`, `update`, `delete`, `promote`)
- `item_id` (UUID, nullable)
- `task_id` (UUID, nullable)
- `timestamp` (TIMESTAMPTZ)
- `metadata` (JSONB)

## Operational Semantics

- Idempotency: writes must be keyed by `event_id` or runtime idempotency key.
- Soft delete first; hard delete by retention workflow.
- Right-to-forget: user/tenant scoped purge must remove all durable memory.
- Encryption: data at rest and in transit is mandatory in production.

## Example Item

```json
{
  "id": "2ecce7e3-cfc0-4907-af06-f4f1f86ed684",
  "tenant_id": "acme",
  "user_id": "user-123",
  "scope": "semantic",
  "content": {
    "fact": "User prefers weekly summary on Mondays",
    "tags": ["preference", "reporting"]
  },
  "confidence": 0.92,
  "source_task_id": "8a4ea31f-d57b-44af-b9bd-30f9cabb18c9",
  "created_at": "2026-03-03T08:00:00Z",
  "expires_at": null,
  "pii_class": "none",
  "version": 1
}
```
