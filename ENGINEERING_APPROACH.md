# Engineering Approach

This document explains the engineering principles and reasoning behind the
GitHub Intelligence backend. `IMPLEMENTATION.md` describes the concrete
architecture and layout; this document explains *why* we made those choices.

## Guiding principle

The goal is **the smallest clean, production-oriented foundation from which we
can safely build the actual product** — industry-level quality without
unnecessary over-engineering.

That means:

- Build only what the current decision requires, nothing speculative.
- Prefer clear boundaries and simple code over clever abstractions.
- Design for the hard parts (sync, idempotency, retries, rate limits, webhooks)
  from day one, but do not over-implement them before the product needs them.
- Keep secrets out of code, configuration files, and logs.

## Why a modular monolith first

- A monolith gives fast iteration, simple local development, and a single
  deployable.
- "Modular" means we enforce clean boundaries between layers and features so
  individual modules can be extracted into separate services later, if and when
  scale or team structure demands it.
- We will **not** introduce distributed infrastructure (Kafka, service meshes,
  Kubernetes, microservices) until there is a demonstrated need.

## Layered boundaries

```text
API
 ↓
Services
 ↓
Repositories
 ↓
Database
```

External systems:

```text
Services
 ↓
Integrations
 ↓
GitHub / external providers
```

Async work:

```text
Services
 ↓
Workers
 ↓
Tasks
```

Rules these boundaries enforce:

- **API routes stay thin** — parse/validate, delegate, format responses.
- **Business logic** lives in `services/` and `domain/`, never in routes or ORM
  models.
- **Database access** lives in `repositories/`.
- **GitHub HTTP communication** lives under `integrations/github/`, never called
  directly from routes or repositories.
- **Async/long-running work** is dispatched to workers/tasks, not executed
  inline in request handlers.
- **No abstraction without a current reason** — we add interfaces/patterns only
  when there is code that benefits from them.
- **No circular imports**, small focused modules, type hints everywhere.

## Source of truth

Two sources of truth, deliberately separated:

- **GitHub is the source of truth for GitHub data** (issues, PRs, commits,
  releases, etc.). We mirror it faithfully rather than inventing it.
- **Our database is the source of truth for application/domain-derived data**
  (e.g., work-item detection results, derived analytics, tenant configuration).

This split keeps synchronization clean: GitHub data flows in via sync/webhooks;
domain data is computed and stored locally.

## The Workspace is the SaaS tenant

- **Workspace** is the tenancy boundary. All domain data is scoped to a
  workspace.
- GitHub connection data is associated with a workspace, but GitHub
  authorization remains separate from application authentication.

## Authentication separation

- **Application authentication** (who can log in to the product) and **GitHub
  authorization** (what GitHub data a workspace can reach) are separate concerns
  and will be implemented separately.
- We will use a third-party auth provider for application auth (provider **not
  yet chosen**).
- The GitHub authorization model (OAuth App vs. GitHub App) is **not yet
  decided** and will be its own integration.

We deliberately avoid choosing either provider now so the foundation does not
lock in an arbitrary decision.

## Design for reliability (from day one, but not over-built now)

Because the product depends heavily on external GitHub APIs, the following are
first-class design principles that shape structure and naming even before they
are implemented:

- **Idempotency** — sync jobs and webhook handlers must be safe to run more than
  once (keyed on stable natural identifiers such as GitHub `node_id`).
- **Retries** — transient failures should be retried with backoff.
- **Rate limits** — respect GitHub rate limits and surface consumption.
- **Webhooks** — prefer events for freshness; use full sync as reconciliation
  and backfill.
- **Synchronization** — eventual consistency; webhooks for delta, sync for
  correctness.

We encode these as design constraints (see `app/domain/synchronization.py`),
not as premature implementations.

## Quality bar

- Type hints everywhere; type-checked with mypy.
- Linted and formatted with Ruff.
- Tests for the foundation from day one.
- Never hardcode secrets; never log secrets or tokens.

## What we deliberately do NOT do yet

Authentication, GitHub OAuth/App installation, GitHub API calls, webhooks,
synchronization, business models, migrations with content, analytics, AI/LLM,
work-item detection, dashboards, billing, notifications. These decisions are
deferred to later phases; the foundation only reserves space for them.
