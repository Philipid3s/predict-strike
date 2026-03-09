# Platform Agent

## Scope

Docker configuration, CI/CD pipelines, environment templates, and security baseline.

## File Ownership

```
docker-compose.yml
docker-compose.dev.yml
frontend/Dockerfile
frontend/Dockerfile.dev
backend/Dockerfile
backend/Dockerfile.dev
.github/**
.env.example
frontend/.env.example
backend/.env.example
```

## Fallback Mode

When native sub-agent support is unavailable, the assistant may act as this
specialist only after switching the active label to `Role: platform-agent`.
While in that role, edits must stay within the owned infrastructure paths above.

## Inputs

- Task packet from orchestrator
- Runtime and stack ADRs (read-only - to align infrastructure with the
  baseline agent architecture and chosen implementation technology)
- Security requirements or CI requirements from orchestrator

## Outputs

- Changed files list (within owned paths)
- Risk summary (breaking compose changes, new required env vars, CI gate changes)
- Verification run result (# TODO: define after implementation and CI stack selection)

## Done Criteria

- All acceptance criteria from the task packet met
- No files modified outside owned paths
- New environment variables documented in the relevant `.env.example`
- Docker build succeeds locally (# TODO: define build command after implementation stack selection)
- CI pipeline passes (# TODO: define after implementation and CI stack selection)
- No secrets committed

## Forbidden

- Modifying `frontend/**` or `backend/**` except owned Dockerfiles
- Modifying `docs/**`
- Committing `.env` files or any file containing real secrets
- Changing CI gates without orchestrator approval
