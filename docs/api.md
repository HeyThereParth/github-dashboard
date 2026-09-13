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

### GET /api/v1/workspaces/{workspace_id}/github/install-url

Returns the GitHub App installation URL with `workspace_id` passed in `state`.
Requires `owner` role.

Response: `GitHubInstallUrlResponse` (`install_url`).

### POST /api/v1/workspaces/{workspace_id}/github/connect

Verifies and associates a GitHub App `installation_id` with the workspace.
Requires `owner` role.

Request: `{"installation_id": 123456}` → `WorkspaceResponse`.

### DELETE /api/v1/workspaces/{workspace_id}/github/disconnect

Clears the GitHub App installation from the workspace.
Requires `owner` role.

Response: `WorkspaceResponse`.

### GET /api/v1/workspaces/{workspace_id}/github/repositories

Lists all repositories accessible via the connected GitHub App installation.
Requires `member` or `owner` role.

- Query params: `page` (default 1), `per_page` (default 100, max 100).
- `400` if the workspace is not connected to GitHub.
- `429` if GitHub's rate limit is exceeded.

Response: `[GitHubRepositoryResponse]`.

## Structure

Remaining namespaces (`users`, `repositories`, `issues`,
`pull_requests`, `people`, `work`, `analytics`, `webhooks`, `sync`) are
placeholders reserved for later phases.

## Conventions

- JSON bodies validated with Pydantic schemas (`app/schemas/`).
- Thin handlers; services contain business logic; repositories access the DB.
- Errors use standard HTTP status codes.

