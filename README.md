# Predict Strike

Predict Strike is an OSINT-driven prediction system for monitoring geopolitical
signals, estimating conflict risk, and comparing internal risk estimates with
prediction market pricing.

The repository starts from a multi-agent development skeleton and is now being
bootstrapped into a domain-specific project with explicit ownership boundaries,
ADR-driven architecture decisions, and a runtime baseline for agent execution.

## Objective

- Collect OSINT signals from aviation, maritime, airspace, satellite, news, and
  social channels.
- Normalize those inputs into structured features and anomaly scores.
- Produce a lightweight conflict risk score that can be compared against market
  probabilities.
- Generate analyst alerts and, later, optional execution or trading signals.

## Planned MVP

- `backend/`: Python services built around FastAPI, scheduled collectors, and
  scoring workflows.
- `frontend/`: React-based operator dashboard for scores, signals, and alerts.
- `data`: SQLite for local persistence and Redis for caching and task support.
- `markets`: Polymarket scanner for question, price, volume, and divergence.
- `alerts`: Telegram, Slack, or email notifications for notable mismatches.

## Project Structure

```text
.
|-- frontend/                 # Operator dashboard and analyst workflows
|-- backend/                  # APIs, collectors, scoring, and alerting logic
|-- docs/
|   |-- adr/                  # Architecture Decision Records
|   |-- api/                  # Planned API contract
|   |-- specs/                # Product and runtime specifications
|   |   `-- technical/
|   |       `-- agent-runtime/ # Core task/tool/retry/state specs
|   `-- guides/               # Kickoff, onboarding, and workflow guides
|-- docker-compose.yml        # Production compose runtime
`-- docker-compose.dev.yml    # Development compose runtime
```

## Run Modes

### Development mode

The project supports both local development outside Docker and containerized
compose-based development.

#### Option A: local development

1. Prepare environment files:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
```

2. Start the backend:

```bash
cd backend
python -m pip install -e .
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Backend API: `http://localhost:8000`

The live Pizza Index primary path now reads `PIZZA_INDEX_DASHBOARD_URL`
(default: `https://www.pizzint.watch/api/dashboard-data`) and keeps the
per-target Google Maps URLs for fallback use with SerpApi.

3. Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Frontend UI: `http://localhost:5173`

This mode is intended for day-to-day feature work. The backend now allows the
local frontend origin through `CORS_ALLOWED_ORIGINS` in `backend/.env`.

#### Option B: development Docker compose

1. Prepare environment files:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
```

2. Start the services:

From the project root you can use the wrapper command:

```powershell
.\run-dev.ps1
```

It forwards to the existing compose dev runtime. Any extra flags are passed
through, for example:

```powershell
.\run-dev.ps1 -d
```

You can still run compose directly if preferred:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Runtime endpoints:

- `frontend`: `http://localhost:5173`
- `backend`: `http://localhost:8000`

The dev compose stack runs the real Vite dev server and the real FastAPI/Uvicorn
backend. Source code is bind-mounted so edits on the host are reflected inside
containers.

#### Optional development checks

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py"

cd frontend
npm test
npm run build
```

### Production mode

1. Prepare environment files:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

2. Start the production stack:

```bash
docker compose up --build -d
```

Runtime endpoints:

- `frontend`: `http://localhost`
- `backend`: `http://localhost:8000`

The production frontend image builds the Vite app and serves the static bundle
from Nginx. The production backend image runs the FastAPI app with Uvicorn.
The frontend build reads `FRONTEND_VITE_API_URL` from the root `.env` file.
For Polymarket, set `POLYMARKET_GAMMA_URL` to the Gamma base URL
`https://gamma-api.polymarket.com/`; the backend normalizes it to the live
events endpoint internally. If Gamma is blocked from your network, the backend
falls back to `POLYMARKET_PIZZINT_BREAKING_URL`
(`https://www.pizzint.watch/api/markets/breaking?window=6h&final_limit=20&format=ticker`)
before degrading to bootstrap data. The `/api/v1/markets/opportunities`
response now exposes `upstream` as `gamma`, `pizzint`, or `bootstrap`. For the
Pizza Index primary feed, set
`PIZZA_INDEX_DASHBOARD_URL` if you need to override the default PizzINT
dashboard endpoint.

#### Stop the production stack

```bash
docker compose down
```

## Kickoff Priorities

1. Lock the MVP scope and implementation stack through ADRs.
2. Build the first ingestion slice for flights, news, and market data.
3. Define normalized feature schemas and an initial weighted risk model.
4. Expose backend endpoints for signal timelines, scores, and market gaps.
5. Add a minimal dashboard for analysts and alert delivery channels.

## Contributing

1. Keep architecture decisions in `docs/adr/`.
2. Update `docs/api/openapi.yml` when backend APIs are introduced or changed.
3. Respect ownership boundaries defined in `AGENTS.md` and
   `docs/agents/ownership.yml`.
