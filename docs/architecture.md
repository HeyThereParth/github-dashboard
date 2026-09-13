# Architecture

See `../IMPLEMENTATION.md` for the canonical architecture description and
`../ENGINEERING_APPROACH.md` for the reasoning behind the decisions.

## Layering

```text
API → Services → Repositories → Database
Services → Integrations → GitHub / external providers
Services → Workers → Tasks
```

## Key boundaries

- API routes stay thin; they parse/validate and delegate to services.
- Business logic lives in `services/` and `domain/`.
- Database access lives in `repositories/`.
- GitHub HTTP communication lives in `integrations/github/`.
- Async work is dispatched to `workers/`.

## Source of truth

- GitHub is the source of truth for GitHub data (mirrored, not invented).
- Our database is the source of truth for application/domain-derived data.
- The **Workspace** is the SaaS tenancy boundary.

## Current state

Foundation only: the API boots, `/health` works, and the layering is in place.
No business functionality is implemented yet.
