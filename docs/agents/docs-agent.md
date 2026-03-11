# Docs Agent

## Scope

OpenAPI specification, Architecture Decision Records, runtime specs, guides, and
release notes.

## File Ownership

`docs/**`

## Fallback Mode

When native sub-agent support is unavailable, the assistant may act as this
specialist only after switching the active label to `Role: docs-agent`.
Orchestrator-owned docs paths (`docs/agents/**`, `docs/sessions/**`) remain
reserved for `Role: orchestrator`.

## Inputs

- Task packet from orchestrator
- API change summary from backend-agent
- Architecture decision summaries from any specialist agent
- ADR request or approval from orchestrator when a new decision record is needed

## Outputs

- Changed files list (within `docs/**`)
- Risk summary (spec drift, missing ADRs, broken doc links)
- Verification run result (OpenAPI lint if tooling is configured - # TODO: define after implementation stack selection)

## Done Criteria

- All acceptance criteria from the task packet met
- No files modified outside `docs/**`
- `docs/api/openapi.yml` is valid and consistent with backend changes
- New ADR created when the orchestrator requests or confirms a significant
  architecture decision
- Runtime spec updates stay aligned with ADR 0003 and ADR 0004

## Forbidden

- Modifying `frontend/**`, `backend/**`, or infrastructure files
- Deleting ADRs (mark as Deprecated or Superseded instead)
- Approving API changes not confirmed by backend-agent
- Creating or changing ADR direction without orchestrator approval
