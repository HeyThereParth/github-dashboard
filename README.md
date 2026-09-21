# GitHub Intelligence Backend

![CI](https://github.com/HeyThereParth/github-dashboard/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Type check](https://img.shields.io/badge/mypy-strict-blue)

A **GitHub engineering-analytics backend**. It ingests repository and pull-request
activity from GitHub — through historical synchronization and real-time webhooks —
mirrors it in PostgreSQL, and serves cycle-time, throughput, and contributor
analytics to a multi-tenant dashboard through a typed, versioned REST API.

## Live links

| | URL |
|---|---|
| Live application (frontend) | <https://github-intelligence.netlify.app/> |
| API (deployed on Render) | <https://github-dashboard-xvea.onrender.com> |
| Health check | <https://github-dashboard-xvea.onrender.com/health> |
| Interactive API docs | <https://github-dashboard-xvea.onrender.com/docs> (local: <http://localhost:8000/docs>) |

## What it does

- **GitHub App integration** — RS256 app authentication, short-lived installation
  tokens with caching, and owner-only workspace connection.
- **Repository discovery and tracking** — list installation repositories and manage
  which ones are mirrored.
- **Historical synchronization** — paginated PR backfill with idempotent upserts and a
  per-job status lifecycle (`pending → processing → completed/failed`).
- **Background sync jobs** — `202 Accepted` start, Redis-backed queue, job status
  polling, and a standalone worker process.
- **GitHub webhook ingestion** — HMAC-SHA256-verified `pull_request` events update the
  local mirror incrementally.
- **Engineering analytics** — repository and workspace-level metrics (see
  [Analytics](#analytics)).

## Engineering highlights

- **Fully async request path**: FastAPI + SQLAlchemy 2.0 (async) + psycopg3 + HTTPX.
- **Redis-backed task queue** (`LPUSH`/`BRPOP` FIFO) with a dedicated worker process
  (`python -m app.workers.worker`) and transparent in-process fallback when Redis is
  unreachable.
- **Idempotent PostgreSQL upserts** (`ON CONFLICT DO UPDATE`) make repeated syncs and
  out-of-order webhook deliveries safe.
- **Cache-aside analytics caching**: 15-minute TTL, repository-level invalidation when
  fresh data arrives, and graceful degradation to direct computation if Redis is offline.
- **JWT/JWKS verification** (PyJWT) against Supabase Auth, isolated behind a
  `TokenVerifier` boundary; the backend maps verified identities to internal users.
- **Strict quality gates**: mypy in strict mode, Ruff lint + format, 124 automated
  tests, and CI running all of them plus SonarQube analysis on every push.

## Architecture

A modular monolith with strict layering:

```text
API  →  Services  →  Repositories  →  PostgreSQL
```

| Layer | Responsibility |
|-------|----------------|
| `api/` | Thin, versioned HTTP routes (`/api/v1`); validation and delegation only |
| `services/` | Business orchestration (sync, analytics, webhooks, workspaces) |
| `repositories/` | Database access only (SQLAlchemy queries, upserts) |
| `models/` / `schemas/` | SQLAlchemy ORM models and Pydantic request/response DTOs |
| `integrations/` | External systems isolated here: GitHub (RS256 auth, REST client, webhook verification) and Supabase token verification |
| `workers/` | Redis queue, standalone worker loop, and background sync tasks |
| `core/` | Typed settings, async engine/session, Redis client, logging, security |
| `domain/` | Reserved for pure domain logic (currently placeholder modules) |

```mermaid
flowchart TD
    Client[React Frontend]
    Supabase[Supabase Auth]
    API[FastAPI API]
    Services[Services]
    Repos[Repositories]
    DB[(PostgreSQL)]
    Redis[(Redis)]
    Worker[Background Worker]
    GH[GitHub API]
    Hook[GitHub Webhooks]

    Client -->|Bearer token| API
    API -->|JWKS verification| Supabase
    API --> Services
    Services --> Repos
    Repos --> DB
    Services -->|analytics cache| Redis
    API -->|enqueue sync job| Redis
    Redis -->|BRPOP| Worker
    Worker --> Repos
    Worker --> GH
    Services -->|installation tokens| GH
    GH --> Hook
    Hook -->|HMAC-verified events| API
```

## Data flow

**Historical synchronization** (establishes full repository state):

```text
POST /sync  →  SyncJob row (202 + job ID)
           →  Redis queue  →  worker (or in-process fallback)
           →  paginated GitHub API  →  idempotent PR upserts
           →  job marked completed  →  analytics cache invalidated
```

**GitHub webhooks** (incremental updates between syncs):

```text
GitHub  →  POST /api/v1/webhooks/github
        →  HMAC-SHA256 signature verification
        →  match tracked repository by GitHub repo ID
        →  PR upsert  →  analytics cache invalidated
```

Both paths exist by design: backfill establishes a consistent baseline, webhooks keep
it fresh without polling the GitHub API.

## Analytics

Cycle time is defined precisely as `merged_at − created_at` for merged pull requests,
reported in hours. Endpoints:

| Endpoint group | Metrics |
|----------------|---------|
| Overview | Total / open / merged / closed-unmerged PRs, merge rate (%), cycle time p50 / p90 / average (hours) |
| Throughput | PRs merged per week (UTC buckets, partial weeks flagged) |
| Activity | PRs created vs merged per day (UTC) |
| Authors | Per-contributor: total PRs, merged PRs, average cycle time |
| Cycle-time trend | Weekly p50 / p90 / average cycle time (default 12 weeks) |

All metrics accept an optional time window (days or weeks) and indicate whether the
response was served from cache (`cached: true`).

## Caching

Analytics use the **cache-aside** pattern: a miss computes the query in PostgreSQL,
stores the serialized response in Redis with a 15-minute TTL, and subsequent hits
return the cached payload. When new PR data arrives (webhook or completed sync), all
cache prefixes for that repository are invalidated. If Redis is unavailable, reads and
invalidation soft-fail and computation falls back to PostgreSQL directly.

## Authentication and authorization

**Application auth** — the frontend sends a Supabase access token; the API verifies the
JWT against the Supabase JWKS, maps the verified identity to an internal `User`,
resolves workspace membership, and enforces the role check:

```text
Supabase access token → JWT/JWKS verification → internal User
→ workspace membership → owner/member role check
```

Tenant isolation is enforced at the query/service level (`401` unauthenticated,
`403` not a member, `404` unknown or unauthorized resource).

**GitHub App auth** — the backend signs RS256 JWTs with the app private key and
exchanges them for short-lived (1-hour) installation tokens, which are cached until
expiry. All GitHub API calls use these installation tokens.

## Technology stack

| Concern | Technology |
|---------|------------|
| Language | Python 3.12 |
| API | FastAPI + Uvicorn (ASGI) |
| Database | PostgreSQL 16 |
| ORM / driver | SQLAlchemy 2.0 (async) / psycopg3 |
| Migrations | Alembic |
| Cache & queue | Redis |
| HTTP client | HTTPX (async) |
| Authentication | Supabase Auth (JWT/JWKS via PyJWT), GitHub App (RS256) |
| External API | GitHub REST API |
| Testing | Pytest (unit + integration) |
| Linting / format | Ruff |
| Type checking | mypy (strict) |
| Containers | Docker + Docker Compose |
| CI/CD | GitHub Actions (+ SonarQube) |
| Deployment | Render |

## API surface

The deployed application registers **27 route paths / 29 operations** under `/api/v1`
(verified from the runtime OpenAPI schema), plus `GET /health`. Categories:

- **Current user** — `GET /api/v1/me`
- **Workspaces** — list, create, retrieve
- **GitHub connection** — install URL, connect, disconnect, list installation repositories
- **Repository tracking** — track, untrack, list tracked repositories
- **Synchronization** — start sync (`202 Accepted`), list sync jobs, poll job status
- **Pull requests** — paginated listing for tracked repositories
- **Analytics** — overview, throughput, activity, authors, cycle-time trend
  (repository-level and workspace-level)
- **Webhooks** — `POST /api/v1/webhooks/github`

Explore interactively at [`/docs`](https://github-dashboard-xvea.onrender.com/docs)
or fetch [`/openapi.json`](https://github-dashboard-xvea.onrender.com/openapi.json).

## Quickstart

```bash
# 1. Create and activate a virtual environment (Python 3.12)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment (defaults work for local dev)
cp .env.example .env          # Windows: copy .env.example .env

# 4. Run the API
uvicorn app.main:app --reload
```

API at <http://localhost:8000>, health at <http://localhost:8000/health>, docs at
<http://localhost:8000/docs>.

To run the background worker in a separate process:

```bash
python -m app.workers.worker
```

## Docker

```bash
docker compose up --build
```

Starts three services: the **backend** (uvicorn with auto-reload), **PostgreSQL 16**,
and **Redis 7**, with health-checked dependencies and persistent volumes. The
background worker is not a separate Compose service — without it, sync jobs run
through the queue's in-process fallback.

## Database migrations

Schema creation is migration-driven — tables are never auto-created at startup.

```bash
alembic upgrade head                          # apply all migrations
alembic revision --autogenerate -m "add ..."  # generate a new migration
```

Current migrations create `users`, `workspaces`, `workspace_members`, `repositories`,
`pull_requests`, `sync_jobs`, and the GitHub installation link on workspaces.

## Testing

**124 tests**: 112 unit tests (no external services required; Supabase verification is
stubbed at the integration boundary) and 12 integration tests that use a PostgreSQL
test database:

```bash
pytest                                        # unit tests only

docker compose up -d postgres
docker exec github-intelligence-postgres psql -U postgres \
  -c "CREATE DATABASE github_intelligence_test;"
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/github_intelligence_test pytest
```

CI runs the full suite against a PostgreSQL service container with coverage.

## Code quality

```bash
ruff check .              # lint
ruff format --check .     # format check (ruff format . to apply)
mypy app tests            # strict type checking
pytest                    # tests
```

GitHub Actions runs all four on every push to `main` and every pull request, applies
migrations against a PostgreSQL service, executes the suite with coverage, and runs a
SonarQube scan.

## Deployment

Deployed on **Render** as a single Python web service defined in `render.yaml`: the
build installs dependencies and applies `alembic upgrade head`, uvicorn serves the API
on `$PORT`, and `/health` is the health-check endpoint. PostgreSQL and Redis are
external services connected via `DATABASE_URL` / `REDIS_URL`; secrets are injected as
synced environment variables; CORS is pinned to the production frontend origin.

The standalone worker is not currently deployed as a separate Render service; in this
topology, sync jobs execute through the queue's in-process fallback, and the worker
process is available for a split deployment when needed.

## Configuration

Typed settings (pydantic-settings) load from environment variables and an optional
`.env` file — see [`.env.example`](.env.example) for the documented set. Key groups
(no secrets are committed):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` / `REDIS_URL` | PostgreSQL and Redis connection URLs |
| `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET` | GitHub App credentials for API authentication and webhook signature verification |
| `SUPABASE_JWKS_URL`, `SUPABASE_JWT_ISSUER`, `SUPABASE_JWT_AUDIENCE` | Supabase Auth JWT verification |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API |
| `ENVIRONMENT`, `DEBUG`, `LOG_LEVEL` | Runtime behavior and structured logging |

## Project structure

```text
app/
├── api/            # HTTP layer: thin routes, auth dependencies, versioned routers
├── core/           # config, async database engine, Redis client, logging, security
├── domain/         # reserved for pure domain logic
├── integrations/   # GitHub (auth, REST client, webhook verification) and Supabase verifier
├── models/         # User, Workspace, WorkspaceMember, Repository, PullRequest, SyncJob
├── repositories/   # database access only
├── schemas/        # Pydantic request/response DTOs
├── services/       # sync, analytics, webhooks, workspaces orchestration
└── workers/        # Redis queue, standalone worker, sync tasks
tests/
├── unit/           # 112 tests, no external services
└── integration/    # 12 tests, PostgreSQL-backed
migrations/         # Alembic versions
docs/               # api.md, architecture.md, database.md
```

## Engineering decisions

Rationale for the major choices lives in dedicated documents:

- [`ENGINEERING_APPROACH.md`](ENGINEERING_APPROACH.md) — layering, async I/O,
  identity boundaries, and integration-isolation principles
- [`IMPLEMENTATION.md`](IMPLEMENTATION.md) — concrete architecture and directory map
- [`docs/architecture.md`](docs/architecture.md),
  [`docs/database.md`](docs/database.md), [`docs/api.md`](docs/api.md)

## Known limitations

- Authorization roles are deliberately simple: `owner` and `member` (no admin tier).
- Webhook handling covers `pull_request` events only; other event types are logged and
  ignored.
- Cycle time measures open-to-merge only (`merged_at − created_at`); review wait time
  and rework are not decomposed.
- Integration tests require a live PostgreSQL instance; they cannot run fully
  self-contained offline.
- Analytics reflect the mirrored data as of the last sync/webhook, not live GitHub state.

## Future work

- Enrich metrics from the existing GitHub integration modules (issues, commits,
  releases) and activate the scaffolded API routers for them.
- Deploy the background worker as a separate process alongside the API.
- AI-assisted engineering insights (PR summaries, risk scoring).
