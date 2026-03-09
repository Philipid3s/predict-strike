# Runtime Errors and Retry Policy

This document defines the runtime error classes and retry behavior used with:
- `task.schema.json`
- `tool.contract.json`

## Error Classes

| Class | Codes | Retry Behavior |
|---|---|---|
| `TRANSIENT` | `TIMEOUT`, `RATE_LIMIT`, `NETWORK` | Retry up to 3 attempts with exponential backoff and jitter |
| `PERMANENT` | `INVALID_INPUT`, `NOT_FOUND`, `POLICY_DENIED` | Do not retry; fail the call immediately |
| `AUTH` | `UNAUTHORIZED`, `FORBIDDEN` | Do not auto-retry; escalate to runtime/operator |
| `INTERNAL` | `INTERNAL` | Retry once; if still failing, mark as failed and dead-letter |

## Retry Defaults

- `max_attempts_transient`: 3
- `max_attempts_internal`: 2 (initial + 1 retry)
- `backoff_base_ms`: 500
- `backoff_multiplier`: 2
- `backoff_jitter_ms`: random value in `[0, 250]`

Backoff formula:

```text
delay_ms = (backoff_base_ms * (backoff_multiplier ^ (attempt - 1))) + random(0, backoff_jitter_ms)
```

## Deadline and Timeout Semantics

- Every tool call must enforce `timeout_ms` from `tool.contract.json`.
- Every task must enforce `deadline_at` from `task.schema.json`.
- A retry must not be scheduled if it would exceed `deadline_at`.

## Idempotency Rules

- Task submission idempotency key: `idempotency_key` in `task.schema.json`.
- Tool-call idempotency key (runtime derived): `task_id + tool_name + stable_hash(args)`.
- Replayed calls with the same idempotency key must return the original terminal result.

## Structured Runtime Events

Runtimes should emit structured events with at least:
- `event_name`
- `task_id`
- `correlation_id`
- `timestamp`
- `attempt` (if applicable)
- `error.code` (if applicable)

Required event names:
- `task_started`
- `tool_called`
- `retry_scheduled`
- `task_failed`
- `task_completed`

## Dead-Letter Queue (DLQ)

Calls or tasks with retry exhaustion must be moved to a DLQ record containing:
- task metadata (`task_id`, `correlation_id`, `contract_version`)
- last error (`code`, `message`, `retryable`)
- retry history (`attempts`, timestamps, delays)
- execution budgets at failure (`max_steps`, `max_tool_calls`, `max_cost_usd`)
