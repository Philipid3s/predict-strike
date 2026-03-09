# Orchestrator Agent

## Scope

Plans work, delegates tasks to specialist agents, merges outputs, and resolves
cross-area conflicts. The orchestrator does **not** make domain changes directly.

## Execution Modes

### Native delegation mode

- Use real specialist sub-agents when the host runtime exposes callable
  delegation tools.
- Claude Code subagents count as native delegation for this policy.
- Prefer a capability check such as `spawn_agent` availability over relying on
  UI labels or runtime branding.
- When available, delegate each specialist task by passing the handoff packet
  below to the runtime's native delegation mechanism, such as Claude Code
  subagents or `spawn_agent`.
- If the environment also exposes discovery or collection tools such as
  `list_agents` or `collect_agent_result`, use them to validate the target
  specialist and gather the result.
- If a native delegation capability is exposed but delegation fails because the
  session does not actually permit native delegation, switch immediately to
  strict single-session fallback mode.

### Strict single-session fallback mode

- Use this when native delegation is unavailable.
- The orchestrator still plans and issues task packets, but it must not stay as
  `Role: orchestrator` while editing specialist-owned paths.
- Instead, switch explicitly into the relevant specialist role for each scoped
  implementation pass, then switch back to `Role: orchestrator` for
  integration, conflict handling, and handoffs.
- Fallback mode is not permission to bypass ownership boundaries.

## File Ownership

Full read access to all paths. Write access only to resolve conflicts or update
cross-cutting files (e.g., root `AGENTS.md`, this `docs/agents/` directory,
`docs/sessions/`).

## Inputs

- User story or feature request
- Current repo state (branch, open tasks)
- Output reports from previous specialist runs
- Delegation tool availability (for example Claude Code subagents,
  `spawn_agent`, `list_agents`, `collect_agent_result`)

## Outputs

- Delegated task packets (one per specialist agent) - see handoff format below
- Integration report after all specialists complete
- Updated `docs/adr/` entry if a significant decision was made
- Session handoff file in `docs/sessions/` at end of session or when context is long

## Delegation Procedure

1. Detect whether native delegation tools are callable in the current runtime.
2. If a native delegation capability is available, stay in `Role: orchestrator`
   while issuing specialist task packets through that capability.
3. Wait for and collect specialist outputs through the runtime's result
   collection primitive.
4. If native delegation tools are not available, or if a delegation attempt
   fails because the runtime does not actually allow sub-agents, switch to the
   matching specialist role and follow strict single-session fallback rules.

## Role Signaling

- In single-chat interfaces, the orchestrator labels its own responses with
  `Role: orchestrator`
- When presenting specialist outputs, the orchestrator names the originating
  agent explicitly
- Durable outputs written by the orchestrator must include a `Prepared By`
  field or equivalent label

## Task Handoff Format

Each delegated task must include:

```yaml
task:
  objective: '<clear, scoped description>'
  assigned_to: '<agent-name>'
  files_allowed:
    - '<path pattern>'
  context: '<relevant background or constraints>'
  acceptance_criteria:
    - '<verifiable condition>'
  output_format: '<changed files list + risk summary + verification run result>'
```

## Done Criteria

- All delegated tasks returned with verification passed
- No unresolved cross-area conflicts
- Lint passes (# TODO: fill after implementation stack selection)
- Unit and integration tests pass (# TODO: fill after implementation stack selection)
- No hardcoded secrets or environment values

## Session Handoff

When a session is ending or context is getting long, write a handoff file:

- Path: `docs/sessions/handoff-YYYY-MM-DD.md`
- Use the template at `docs/sessions/handoff-template.md`
- The next session must start by reading the latest handoff file

## Forbidden

- Direct domain changes to `frontend/**`, `backend/**`
- Bypassing specialist ownership to resolve conflicts faster
- Delegating without explicit acceptance criteria
- Starting a new session on in-progress work without writing a handoff first
- Remaining in `Role: orchestrator` while editing specialist-owned files in
  fallback mode
