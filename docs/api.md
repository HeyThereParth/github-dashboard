# API

## Versioning and prefix

- All product endpoints live under `/api/v1`.
- Health check: `GET /health` (operational, unversioned).

## Authentication

All product endpoints except `/health` require a Supabase-issued bearer token:

```http
Authorization: Bearer <supabase-access-token>
```

- `401` for a missing, malformed, or invalid token.
- The backend verifies the token and resolves/creates the internal `User`.

## Endpoints

### GET /api/v1/me

Returns the authenticated user's application profile (no provider tokens).

Response: `UserResponse` (`id`, `email`, `name`, `avatar_url`, `created_at`,
`updated_at`).

### POST /api/v1/workspaces

Creates a workspace; the caller becomes its `owner`. Transactional — a workspace
is never created without its owner membership.

Request: `{"name": "..."}` → `201` + `WorkspaceResponse`.

### GET /api/v1/workspaces

Lists the caller's workspaces. Response: `[WorkspaceSummary]`.

### GET /api/v1/workspaces/{workspace_id}

Returns a workspace; requires membership.

- `404` if the workspace does not exist.
- `403` if the caller is not a member.

Response: `WorkspaceResponse`.

## Structure

Remaining namespaces (`users`, `github`, `repositories`, `issues`,
`pull_requests`, `people`, `work`, `analytics`, `webhooks`, `sync`) are empty
`APIRouter` placeholders.

## Conventions

- JSON bodies validated with Pydantic schemas (`app/schemas/`).
- Thin handlers; services contain business logic; repositories access the DB.
- Errors use standard HTTP status codes.

