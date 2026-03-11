# AGENTS.md

Universal agent instructions for this repository.
Designed to be usable from any agentic IDE or CLI that supports in-repo
instruction files. `AGENTS.md` is the primary shared contract; tool-specific
entrypoints such as `CLAUDE.md` should import or reference it.

---

## Project Overview

Predict Strike is an OSINT-driven prediction system focused on collecting
geopolitical and military-adjacent signals, converting them into structured
risk features, and comparing internal conflict-risk estimates with prediction
market pricing.

The repository keeps the built-in multi-agent development workflow and default
runtime baseline for task execution, tool calling, retries, and memory
management while the product-specific implementation is being planned.

## Architecture

| Layer    | Path        | Role                                                    |
| -------- | ----------- | ------------------------------------------------------- |
| Frontend | `frontend/` | Analyst/operator dashboard for scores, signals, alerts  |
| Backend  | `backend/`  | Collectors, APIs, risk scoring, market scanning, alerts |
| Docs     | `docs/`     | ADRs, product specs, runtime specs, API specs, guides   |

## Development Commands

### Start (dev)

```bash
docker compose -f docker-compose.dev.yml up --build
```

### Frontend and Backend

Initial planned stack for this project:

- Backend/API: Python + FastAPI
- Frontend: React
- Database: SQLite
- Cache/queue support: Redis
- Scheduling/workers: Celery and/or cron

Document any later deviations from this baseline in `docs/adr/`.

### Tests

Define and document service test commands for the chosen implementation stack.

## Code Conventions

- All new architecture decisions -> `docs/adr/` (use ADR format)
- Runtime contract and memory model changes -> update `docs/specs/technical/agent-runtime/`
- API changes -> update `docs/api/openapi.yml`
- Environment variables -> document in `.env.example` files
- Never commit `.env` files

## Key Files

| File                                  | Purpose                               |
| ------------------------------------- | ------------------------------------- |
| `docker-compose.yml`                  | Production compose template           |
| `docker-compose.dev.yml`              | Development compose template          |
| `docs/adr/`                           | Architecture Decision Records         |
| `docs/specs/technical/agent-runtime/` | Core runtime contract and state model |
| `docs/api/openapi.yml`                | OpenAPI specification                 |
| `.env.example`                        | Root environment variable reference   |

## Multi-Agent Workflow

This project uses an **orchestrator + specialist agents** model.
See [ADR 0002](docs/adr/0002-multi-agent-pattern.md) for the decision record.

| Agent          | Owned paths                                                                            | Contract                                           |
| -------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------- |
| orchestrator   | `**` (conflict resolution only)                                                        | [orchestrator.md](docs/agents/orchestrator.md)     |
| frontend-agent | `frontend/**`                                                                          | [frontend-agent.md](docs/agents/frontend-agent.md) |
| backend-agent  | `backend/**`                                                                           | [backend-agent.md](docs/agents/backend-agent.md)   |
| docs-agent     | `docs/**`                                                                              | [docs-agent.md](docs/agents/docs-agent.md)         |
| platform-agent | compose, service Dockerfiles, CI, env templates                                        | [platform-agent.md](docs/agents/platform-agent.md) |
| qa-agent       | read-only on specs + implementation, writes to `docs/reports/` and `tests/acceptance/` | [qa-agent.md](docs/agents/qa-agent.md)             |

Machine-readable ownership map: [`docs/agents/ownership.yml`](docs/agents/ownership.yml)

Each agent operates only within its declared paths. The orchestrator is the sole
resolver of cross-area conflicts. Every delegated task must follow the handoff
format defined in [orchestrator.md](docs/agents/orchestrator.md).

## Execution Mode Enforcement

`AGENTS.md` defines workflow policy and ownership, but it does not by itself
instantiate native sub-agents in every host runtime. Therefore this repository
defines two allowed execution modes:

1. **Native delegation mode**
   - The host runtime exposes real sub-agent/task delegation tools.
   - Native delegation is enabled by capability detection, not by UI labels or
     runtime branding alone.
   - When a native delegation capability is available, such as Claude Code
     subagents or a delegation tool like `spawn_agent`, the orchestrator should
     delegate specialist work through that capability using the task packet
     format defined in `docs/agents/orchestrator.md`.
   - Native delegation transport types such as `worker`, `default`, or host
     runtime subagent classes are implementation details only. They do not
     replace repository roles such as `frontend-agent`, `backend-agent`,
     `docs-agent`, `platform-agent`, or `qa-agent`.
   - Exactly one session participant may act as `Role: orchestrator`. Delegated
     agents must always adopt a specialist role and must never identify
     themselves as `Role: orchestrator`.

2. **Strict single-session fallback mode**
   - Used when the host runtime does not expose native sub-agent delegation
     tools, or when those tools are unavailable at runtime.
   - The assistant must still follow specialist ownership and role-switching
     rules as if each specialist were a separate worker.

### Delegation capability detection

- Treat native delegation as available only when the active environment exposes
  a callable delegation capability, such as Claude Code subagents or a
  delegation primitive like `spawn_agent`.
- If the environment exposes helper discovery tools such as `list_agents` or
  `collect_agent_result`, use them to confirm and complete native delegation.
- Do not assume native delegation is available solely because the host mentions
  `experimental`, `beta`, or similar labels.
- If a delegation tool is visible but fails because delegation is unsupported in
  the current session, immediately fall back to strict single-session mode and
  continue the task without blocking.

### Mandatory rules in native delegation mode

- Exactly one active orchestrator may exist for the session.
- The main session is the only place allowed to use `Role: orchestrator`.
- Each delegated task must name the repository specialist explicitly via
  `assigned_to`.
- Each delegated task must include an `active_role` field that matches the
  assigned repository specialist.
- The delegated task message itself must not begin with
  `Role: orchestrator`, even if the parent orchestrator authored the handoff.
- Delegated agents must begin their own task output with
  `Role: <assigned specialist>`.
- Delegated agents must not present themselves as generic coordinators,
  orchestrators, or unlabeled workers in user-visible summaries.
- File ownership is determined by repository role, not by runtime transport
  type.

### Mandatory rules in fallback mode

- Exactly one active role may be used at a time.
- `Role: orchestrator` is for planning, decomposition, conflict resolution,
  integration, and handoff writing only.
- The orchestrator must not remain the active role while editing
  `frontend/**`, `backend/**`, `docs/**` (except `docs/agents/**`,
  `docs/sessions/**`, and orchestrator-owned ADR work), `tests/acceptance/**`,
  or platform-owned files.
- For a single-area task, the assistant must switch immediately to the matching
  specialist role before making edits.
- For cross-area work, the assistant must:
  - start as `Role: orchestrator`
  - emit explicit task packets per specialist scope
  - switch roles sequentially while working each owned area
  - return to `Role: orchestrator` only for integration summary, conflict
    handling, or session handoff
- Role labels are not cosmetic; they must match the owned paths being edited.
- `Pragmatic single-agent` behavior is not the default. It is allowed only when
  the user explicitly requests it.

## Role Signaling Convention

Most chat interfaces show only one assistant stream. To make the active role
visible, agent outputs should label themselves explicitly.

- Start orchestration messages with `Role: orchestrator`
- Start specialist-style messages with `Role: <agent-name>`
- Use the same label in handoff files, QA reports, and other durable outputs
- When the orchestrator summarizes specialist work, it should state which agent
  perspective produced each result

Example labels:

- `Role: orchestrator`
- `Role: backend-agent`
- `Role: docs-agent`

For native delegation, the runtime may still use generic transport names such
as `worker` or `default`, but those are not valid substitutes for repository
role labels in task packets, summaries, reports, or handoffs.

**Session continuity:** At the end of a long session or before starting a new one,
the orchestrator writes a session handoff file to `docs/sessions/` using the template
at `docs/sessions/handoff-template.md`. Every new session on in-progress work must
start by reading the latest handoff file.

### Session Handoff Trigger

Treat a plain-language session-close message as an instruction to write the
handoff file before ending the session.

Equivalent trigger phrases include:

- `end of session`
- `handoff session`
- `write the handoff`
- `that's all for today`
- `we stop here`
- `let's continue later`

When triggered, the orchestrator should:

- create or update `docs/sessions/handoff-YYYY-MM-DD.md`
- use `docs/sessions/handoff-template.md`
- set `Prepared By` to the active role, usually `orchestrator`
- summarize completed work, decisions, current state, open questions, next task,
  files modified, and risks/watch points

## Project Kickoff Bootstrap

When this template is used to start a real project, the first bootstrap step is
to replace the skeleton identity with the new project identity.

- Ask for the project name if the kickoff request does not provide it
- Rename the project across repository-facing documentation
- Remove or replace skeleton-repository clone links and placeholder repo references
- Make README-style files read like the new project, not like a generic template

At minimum, review and update:

- `README.md`
- `AGENTS.md`
- relevant files under `docs/`
- placeholder clone URLs and repository references

## Agent Behavior Guidelines

- Prefer editing existing files over creating new ones.
- Do not commit `.env` or secrets.
- Before modifying a file, read it first to understand context.
- Keep solutions minimal and avoid over-engineering.
- When adding architecture decisions, create a new ADR in `docs/adr/`.
- The orchestrator decides when an ADR is required; `docs-agent` authors the
  ADR file unless the user explicitly requests a different mode of working.
- Respect file ownership defined in `docs/agents/ownership.yml`.
- If the runtime lacks native sub-agent support, enforce the strict fallback
  rules above rather than collapsing specialist work into `Role: orchestrator`.
