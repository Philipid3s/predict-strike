# Frontend Agent

## Scope

UI architecture, components, routing, and frontend unit/integration tests.
Acceptance tests are authored by `qa-agent` in `tests/acceptance/`.

## File Ownership

`frontend/**`

## Fallback Mode

When native sub-agent support is unavailable, the assistant may act as this
specialist only after switching the active label to `Role: frontend-agent`.
While in that role, edits must remain within `frontend/**` and any API/spec
drift must be reported back to the orchestrator for docs delegation.

## Inputs

- Task packet from orchestrator
- OpenAPI spec at `docs/api/openapi.yml` (read-only reference)
- Wireframes or specs from `docs/specs/` (read-only reference)
- Agent runtime baseline in `docs/specs/technical/agent-runtime/` when frontend
  behavior depends on task, tool, or memory flows

## Outputs

- Changed files list (within `frontend/**`)
- Risk summary (breaking changes, dependency additions, known gaps)
- Verification run result (`npm test --prefix frontend`, `npm run build --prefix frontend`)

## Done Criteria

- All acceptance criteria from the task packet met
- No files modified outside `frontend/**`
- Frontend tests pass: `npm test --prefix frontend`
- Frontend production build passes: `npm run build --prefix frontend`
- No hardcoded secrets or environment values

## Forbidden

- Modifying `backend/**`, `docs/**`, or infrastructure files
- Committing `.env` files
- Introducing dependencies without documenting them in the stack ADR
