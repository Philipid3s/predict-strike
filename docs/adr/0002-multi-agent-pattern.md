# ADR 0002: Multi-Agent Orchestration Pattern

## Status

Accepted

## Date

2026-02-27

## Context

As the project grows, multiple AI agents (and human developers following agent-like workflows)
will work concurrently on different areas of the codebase. Without a defined protocol,
this creates risk of conflicting changes, unclear ownership, and inconsistent outputs.

## Decision

Adopt an **orchestrator + specialist agents** model.

- A single **orchestrator** plans work, delegates tasks, and resolves cross-area conflicts.
- Specialist agents (**frontend**, **backend**, **docs**, **platform**, **qa**) each own a defined
  file scope and operate within it autonomously.
- Agent contracts are documented in `docs/agents/` — one file per agent.
- File ownership is declared in `docs/agents/ownership.yml` for both human reference
  and automated conflict checks.
- `AGENTS.md` remains the top-level policy document; agent contracts extend it
  without overriding it.

The orchestrator trigger mechanism (human, CI event, or script) is intentionally left
open until the stack and CI pipeline are chosen.

## Consequences

- Clear ownership prevents merge conflicts between concurrent agents.
- Agent contracts serve as machine-readable specs for AI agents and onboarding docs for humans.
- Service-specific sections (lint, test commands, done criteria) are placeholder
  TODOs until the implementation stack is decided (see future ADR).
- The orchestrator role adds coordination overhead; acceptable given the conflict
  prevention benefit at scale.
