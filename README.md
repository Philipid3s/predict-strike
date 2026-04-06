# Predict Strike

Predict Strike is an OSINT-driven monitoring system for collecting geopolitical
and military-adjacent signals, converting them into structured risk features,
and comparing internal conflict-risk estimates with prediction-market pricing.

The current repository includes a working FastAPI backend, a React operator
dashboard, SQLite-backed snapshot history, and source slices for OpenSky, FAA
NOTAM, GDELT, Pizza Index activity, market opportunities, and analyst alerts.

## Current Capabilities

- Collect and normalize signal slices for `OpenSky Network`, `NOTAM Feed`,
  `GDELT`, and `Pizza Index Activity`
- Compute a transparent conflict-risk score from the latest signal snapshot
- Pull market opportunities and compare model outputs with Polymarket pricing
- Persist latest snapshots and historical evaluation artifacts in SQLite
- Evaluate and store analyst-facing alerts from the current opportunity set
- Expose dashboard and source-detail refresh flows with distinct
  source-refresh versus signal-refresh semantics

## Repository Structure

```text
.
|-- frontend/                 # React operator dashboard
|-- backend/                  # FastAPI API, collectors, services, tests
|-- docs/
|   |-- adr/                  # Architecture decisions
|   |-- api/                  # OpenAPI contract
|   |-- guides/               # Setup and operational guides
|   |-- ref/                  # Reference material and fixtures
|   `-- specs/                # Product and technical specifications
|-- docker-compose.yml        # Production stack
|-- docker-compose.dev.yml    # Development stack
`-- AGENTS.md                 # Repository workflow and ownership rules
```

## Local Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker Desktop or Docker Engine with Compose support

### Environment Files

Create local environment files before running the app:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Do not commit `.env` files, API keys, OAuth credentials, or local databases.

### Run With Docker

```bash
docker compose -f docker-compose.dev.yml up --build
```

PowerShell wrapper:

```powershell
.\run-dev.ps1
```

### Run Without Docker

Backend:

```bash
cd backend
python -m pip install -e .
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## Runtime Endpoints

- Frontend UI: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- OpenAPI reference: [`docs/api/openapi.yml`](/D:/Projects/predict-strike/docs/api/openapi.yml)

Primary API groups:

- `/api/v1/signals`
- `/api/v1/risk`
- `/api/v1/markets`
- `/api/v1/alerts`
- `/api/v1/pizza-index`

## Testing

Backend:

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py"
```

Frontend:

```bash
cd frontend
npm test
npm run build
```

## NOTAM Configuration

The FAA NOTAM integration uses OAuth client credentials and environment-scoped
configuration. Start with:

- [`docs/guides/notam-faa-integration.md`](/D:/Projects/predict-strike/docs/guides/notam-faa-integration.md)
- [`docs/ref/NOTAM SAMPLES/README.md`](/D:/Projects/predict-strike/docs/ref/NOTAM%20SAMPLES/README.md)
- [`backend/.env.example`](/D:/Projects/predict-strike/backend/.env.example)

The backend supports `NOTAM_ENV` plus scoped overrides such as
`NOTAM_TEST_*` and `NOTAM_PRODUCTION_*`.

## Documentation Map

- [`docs/guides/getting-started.md`](/D:/Projects/predict-strike/docs/guides/getting-started.md): setup and first-run flow
- [`docs/specs/initial-draft-project-spec.md`](/D:/Projects/predict-strike/docs/specs/initial-draft-project-spec.md): product scope and implementation shape
- [`docs/specs/README.md`](/D:/Projects/predict-strike/docs/specs/README.md): spec layout and runtime baseline
- [`docs/adr/`](/D:/Projects/predict-strike/docs/adr): architecture decisions
- [`docs/api/openapi.yml`](/D:/Projects/predict-strike/docs/api/openapi.yml): API contract

## Workflow Notes

- Keep architecture decisions in `docs/adr/`
- Update `docs/api/openapi.yml` when API behavior changes
- Respect ownership and delegation rules in [`AGENTS.md`](/D:/Projects/predict-strike/AGENTS.md)
- Never commit secrets, credentials, `.env` files, or generated SQLite data
