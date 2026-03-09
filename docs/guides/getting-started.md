# Getting Started

This guide bootstraps the repository as **Predict Strike**, an OSINT-driven
conflict-risk and prediction-market monitoring project.

## Prerequisites

- Docker 24+ (recommended for first run)
- Git

Optional (if running without Docker):
- Node.js 20+ for the React frontend toolchain
- Python 3.12+ for the FastAPI backend and scheduled workers
- Redis when running background jobs or caching locally

## Quick Start (Docker)

```bash
# 1. Open the repository root
cd predict-strike

# 2. Create local env files
cp .env.example .env
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env

# 3. Start project services
docker compose -f docker-compose.dev.yml up --build
```

The current containers still provide a bootstrap baseline. Service scaffolding
should align with the accepted MVP stack in
`docs/adr/0008-predict-strike-mvp-scope-and-initial-stack.md` while preserving
the runtime contracts in `docs/specs/technical/agent-runtime/`.

## Local Development (Without Docker)

Set up `frontend/` and `backend/` using the selected React and FastAPI stack,
then run each service with its own native dev command.

## Testing

Define and document test commands for the frontend, backend, and any background
workers as implementation lands. Keep docs, CI, and the agent contracts in
sync.
