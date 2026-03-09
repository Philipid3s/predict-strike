# ADR 0003: Agent Runtime Contract and Retry Policy

## Status
Accepted

## Date
2026-03-03

## Context
The project has a multi-agent development model and is intended to serve as an
AI-agent system skeleton. Without a shared runtime contract, different
executors and tools can diverge in request shape, failure handling, and retry
behavior. This increases integration risk, makes observability inconsistent, and
creates non-deterministic behavior across environments.

## Decision
Define and adopt a versioned runtime contract with three normative artifacts:

1. `docs/specs/technical/agent-runtime/task.schema.json`
   - Canonical task envelope for all agent task submissions.
   - Includes execution budgets, idempotency key, and tool allowlist policy.

2. `docs/specs/technical/agent-runtime/tool.contract.json`
   - Canonical request/response envelope for tool invocations.
   - Includes status, duration, and standardized error object.

3. `docs/specs/technical/agent-runtime/runtime-errors.md`
   - Error classification model and deterministic retry semantics.
   - Includes backoff defaults, deadline behavior, and dead-letter handling.

Contract versioning rules:
- `contract_version` is required in task payloads.
- Unknown major versions must be rejected.
- Minor versions may add optional fields but must not break existing required
  fields or semantics.

Minimum runtime behavior requirements:
- Enforce idempotency for task submission and tool invocation.
- Enforce per-call timeout and overall task deadline.
- Emit structured lifecycle events for observability:
  `task_started`, `tool_called`, `retry_scheduled`, `task_failed`, `task_completed`.

## Consequences
Positive:
- Agent execution behavior is consistent across implementations.
- Tool integration and retries become testable and deterministic.
- Observability and incident analysis improve via shared events and error codes.

Trade-offs:
- Initial overhead to implement schema validation and retry middleware.
- Future contract changes require version management discipline.
