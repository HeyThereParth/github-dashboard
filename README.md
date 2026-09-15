# GitHub Intelligence Backend

Backend service for GitHub Intelligence — a SaaS application that ingests,
organizes, and derives insights from GitHub data.

> **Current status: Production Ready on Render with Background Task Queue.**
> Features completed: Supabase Auth & RBAC (Phase 1), GitHub App Integration (Phase 2),
> Repository & Pull Request Mirroring (Phase 3), Dual-Sync Ingestion with HMAC Webhooks (Phase 4),
> Cycle Time & Throughput Analytics with Redis Cache-Aside (Phase 5), and Asynchronous
> Task Queue with Background Worker (Phase 6). Live at `https://github-dashboard-xvea.onrender.com`.

## What this backend is

- A **FastAPI** application exposing a versioned REST API (`/api/v1`).
- A **modular monolith** with clean layering (API → Services → Repositories →
  Database) and isolated external integrations (`integrations/github`).
- A **PostgreSQL**-backed data store (via SQLAlchemy + Alembic) and **Redis** for
  caching/queues.
- A system designed for **synchronization** with GitHub (webhooks + sync,
  idempotency, retries, rate limits), to be built in later phases.

## Architecture direction

| Layer | Responsibility |
|-------|----------------|
| `api/` | Thin HTTP routes; validate/parse and delegate |
| `services/` | Business/domain orchestration |
| `repositories/` | Database access only |
| `integrations/` | External systems (auth, GitHub) isolated here |
| `workers/` | Async/background work |
| `domain/` | Pure domain logic, infrastructure-free |

See `ENGINEERING_APPROACH.md` (why) and `IMPLEMENTATION.md` (what).

## Technology stack

- **Python 3.12**
- **FastAPI** + **Uvicorn** (web framework / ASGI server)
- **Pydantic** + **pydantic-settings** (validation / typed config)
- **SQLAlchemy 2.0** (async ORM) + **psycopg3** (PostgreSQL driver)
- **Alembic** (migrations)
- **PostgreSQL** (database) and **Redis** (cache/queue)
- **HTTPX** (async HTTP client for GitHub)
- **Pytest** (tests), **Ruff** (lint/format), **mypy** (type checking)
- **Docker / Docker Compose** (local dev), **GitHub Actions** (CI)

## Local setup

```bash
# 1. Create and activate a virtual environment (Python 3.12)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment (optional; defaults work for local dev)
#    Copy and edit as needed:
#    cp .env.example .env        (Windows: copy .env.example .env)

# 4. Run the API
uvicorn app.main:app --reload
```

The API will be available at <http://localhost:8000>. Health check:
<http://localhost:8000/health>. Interactive docs: <http://localhost:8000/docs>.

## Environment variables

See `.env.example` for the full documented set. Key variables:

| Variable | Purpose | Default (dev) |
|----------|---------|---------------|
| `APP_NAME` | Application name | `GitHub Intelligence Backend` |
| `ENVIRONMENT` | `development` / `production` | `development` |
| `DEBUG` | SQL echo / debug toggles | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DATABASE_URL` | PostgreSQL connection URL | `postgresql+psycopg://postgres:postgres@localhost:5432/github_intelligence` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `GITHUB_*` | GitHub integration placeholders | none (empty) |
| `SUPABASE_JWKS_URL`, `SUPABASE_JWT_ISSUER`, `SUPABASE_JWT_AUDIENCE` | Supabase Auth token verification | none (empty) / `authenticated` |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API | `http://localhost:5173,http://127.0.0.1:5173` |

GitHub placeholders (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, etc.) exist for
future configuration only; no real values are committed and no GitHub auth is
implemented. Supabase Auth requires `SUPABASE_JWKS_URL` and
`SUPABASE_JWT_ISSUER` for token verification.

## Running tests

```bash
pytest
```

Unit tests (`tests/unit`) run without external services. Integration tests
(`tests/integration`) require a PostgreSQL test database:

```bash
docker compose up -d postgres
docker exec github-intelligence-postgres psql -U postgres \
  -c "CREATE DATABASE github_intelligence_test;"
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/github_intelligence_test pytest
```

The Supabase token-verification boundary is stubbed in tests, so no real Supabase
project is required.

## Linting, formatting, type checking

```bash
ruff check .              # lint
ruff format --check .     # format check (ruff format . to apply)
mypy app tests            # type checking
```

## Docker usage

```bash
docker compose up --build
```

This starts the backend, PostgreSQL, and Redis. The backend is available at
<http://localhost:8000>.

## Migrations

Alembic is configured (`alembic.ini`, `migrations/env.py`). The initial migration
creates `users`, `workspaces`, and `workspace_members`.

```bash
alembic upgrade head                          # apply
alembic revision --autogenerate -m "add ..."  # generate a new migration
```

## Roadmap & Future Enhancements
- AI/LLM PR summaries and risk scoring
- Advanced team invitations, role customization, and billing (Stripe)
- Slack / Discord webhook alerts for engineering bottlenecks

## Repository layout

See `IMPLEMENTATION.md` for a full directory map.
