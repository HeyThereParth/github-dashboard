# Implementation

Concrete architecture, stack, and layout for the GitHub Intelligence backend.
See `ENGINEERING_APPROACH.md` for the reasoning behind these choices.

## Current status

- **Phase 1 (Identity & Workspace) implemented.** Supabase Auth is the external
  identity provider; the backend maintains internal `User` records, `Workspace`
  tenants, and `WorkspaceMember` membership, with authentication and workspace
  authorization enforced at the API layer.
- **Implemented:** `/health`, `GET /api/v1/me`, `POST /api/v1/workspaces`,
  `GET /api/v1/workspaces`, `GET /api/v1/workspaces/{id}`; the first Alembic
  migration (`users`, `workspaces`, `workspace_members`).
- **Not implemented:** GitHub authorization/OAuth, GitHub API calls, webhooks,
  synchronization, GitHub/domain models, analytics, AI/LLM, billing,
  notifications.

## Technology stack

| Concern | Technology |
|---------|------------|
| Language | Python 3.12 |
| Web framework | FastAPI |
| ASGI server | Uvicorn |
| Validation / config | Pydantic + pydantic-settings |
| ORM | SQLAlchemy 2.0 (async) |
| PostgreSQL driver | psycopg3 (`psycopg`) |
| Migrations | Alembic |
| Database | PostgreSQL |
| Cache/queue | Redis (redis-py) |
| HTTP client | HTTPX (async) |
| Workers | async tasks (queue/broker to be finalized) |
| Testing | Pytest |
| Lint/format | Ruff |
| Type checking | mypy |
| Containerization | Docker + Docker Compose |
| CI | GitHub Actions |

## Directory structure

```text
github-intelligence-backend/
├── app/
│   ├── main.py               # app factory + lifespan + /health
│   ├── api/                  # HTTP layer (thin routes + dependencies)
│   │   └── v1/               # versioned resource routers (placeholders)
│   ├── core/                 # config, database, security, logging
│   ├── models/               # SQLAlchemy ORM models (User, Workspace, WorkspaceMember)
│   ├── schemas/              # Pydantic DTOs (request/response)
│   ├── repositories/         # database access only
│   ├── services/             # business/domain orchestration
│   ├── integrations/         # external systems isolated here
│   │   ├── auth/             # Supabase token verification boundary
│   │   └── github/           # GitHub client/auth/domain integrations
│   ├── workers/              # async worker + tasks
│   └── domain/               # pure domain logic (infrastructure-free)
├── tests/
│   ├── unit/                 # unit tests
│   ├── integration/          # tests needing DB/external services
│   └── e2e/                  # end-to-end tests
├── migrations/               # Alembic migrations
├── scripts/                  # operational scripts
├── docs/                     # architecture, api, database, decision records
├── .github/workflows/ci.yml  # CI pipeline
├── .env.example              # documented environment variables
├── Dockerfile                # production-oriented image
├── docker-compose.yml        # local dev: backend + postgres + redis
├── requirements.txt          # runtime + dev dependencies
├── pyproject.toml            # pytest/ruff/mypy configuration
├── alembic.ini               # Alembic configuration
├── ENGINEERING_APPROACH.md   # principles / reasoning (this repo)
└── IMPLEMENTATION.md         # architecture / layout (this doc)
```

## Configuration

`app/core/config.py` defines a typed `Settings` (pydantic-settings) loaded from
environment variables and an optional `.env` file. It tracks:

- application identity, environment, debug, and log level
- `DATABASE_URL` and `REDIS_URL`
- GitHub integration placeholders (API URL, client/app credentials) — no real
  values, no auth model decided

See `.env.example` for the documented variable set.

## Database

`app/core/database.py` provides:

- an async engine and `async_sessionmaker`
- a declarative `Base`
- a `get_db` FastAPI dependency

Tables are **not** auto-created on startup; Alembic owns the schema.
`migrations/env.py` reads `Base.metadata` and `DATABASE_URL`. The initial
migration creates `users`, `workspaces`, and `workspace_members` (see
`docs/database.md`).

## Authentication (Phase 1)

Supabase Auth issues the tokens; the backend verifies them and owns application
identity and authorization.

- Verification is isolated behind `TokenVerifier` (`app/integrations/auth/`).
  The default `SupabaseTokenVerifier` verifies JWTs against the project's JWKS
  (asymmetric keys) using PyJWT.
- The backend never issues tokens, stores passwords, or manages sessions.
- A verified identity is mapped to an internal `User` via
  `auth_provider_user_id` (unique); the Supabase user id is never our primary key.

```text
Request → Authorization header → TokenVerifier.verify → VerifiedIdentity
        → UserService.get_or_create_user → internal User
```

## Authorization (Phase 1)

Authorization is application-side and tenant-scoped:

```text
authenticated User → WorkspaceMember → allowed / denied
```

- `401` when not authenticated; `403` when authenticated but not a member.
- The reusable `get_accessible_workspace` dependency enforces membership and
  will later protect repositories, issues, PRs, people, work items, and analytics.

## API direction

- All product endpoints under `/api/v1`.
- Implemented: `GET /me`; `POST /workspaces`, `GET /workspaces`,
  `GET /workspaces/{id}`.
- Remaining namespaces (`github`, `repositories`, `issues`, `pull_requests`,
  `people`, `work`, `analytics`, `webhooks`, `sync`) are empty `APIRouter`
  placeholders.
- RESTful JSON; Pydantic DTOs for request/response; thin handlers.

## Entities

### Implemented (Phase 1)

- **User** — internal application user, linked to a Supabase identity via the
  unique `auth_provider_user_id`. `id` is our internal UUID and primary key.
- **Workspace** — the SaaS tenant boundary.
- **WorkspaceMember** — joins users to workspaces with a role (`owner`, `member`);
  unique on `(workspace_id, user_id)`.

### Direction (later phases)

- **Repository** — mirror of a GitHub repository.
- **Issue / PullRequest / Person / Commit / Release** — mirrors of GitHub
  objects.
- **Work item** — domain-derived (later).
- **Sync run / state** — synchronization bookkeeping (later).

GitHub-derived entities are mirrors keyed by stable GitHub identifiers; domain
entities are computed and owned locally.

## Synchronization strategy (direction)

- **Webhooks** for delta updates (freshness).
- **Sync** endpoints/jobs for backfill and reconciliation (correctness).
- **Idempotent** by stable natural keys (e.g., GitHub `node_id`).
- **Retries** with backoff for transient failures.
- **Rate-limit aware**; consumption tracked and respected.
- GitHub data stored as a mirror; domain data derived and stored locally.

## Security

- Secrets come from environment variables only; no secrets in code or config.
- Never log secrets or tokens; the API never returns provider tokens.
- Application auth uses Supabase Auth (JWT verification); GitHub auth is separate
  and deferred.
- Authorization enforced via workspace membership (`401` unauthenticated,
  `403` not-a-member, `404` unknown).
- Database uniqueness protects identity (`auth_provider_user_id`) and membership
  (`workspace_id, user_id`).
- CORS, TLS termination, and rate limiting will be added when network exposure
  is decided.

## Observability

- Structured logging configured via `app/core/logging.py`.
- `GET /health` liveness endpoint.
- Metrics/tracing deferred until there is a reason.

## Testing

- `tests/unit` — auth dependency 401 paths and `/health` (no DB).
- `tests/integration` — user provisioning, workspace CRUD, authorization, and
  tenant isolation against a PostgreSQL test database (Docker). The Supabase
  boundary is stubbed.
- `tests/e2e` — reserved for later.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Or with Docker:

```bash
docker compose up --build
```

## Future evolution

1. ~~Choose and integrate the third-party auth provider.~~ (done — Supabase Auth)
2. Decide the GitHub authorization model (OAuth App vs. GitHub App).
3. Add GitHub integrations (client, auth, sync, webhooks).
4. Add GitHub/domain models + migrations + repositories.
5. Add workers/tasks for sync and long-running work.
6. Add analytics/domain services.
7. Extract modules into services only if scale/team structure demands it.
