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

### POST /api/v1/workspaces/{workspace_id}/repositories/track

Enables tracking for a repository accessible through the connected GitHub App.
Requires `owner` role.

- Request: `{"owner": "...", "repo": "..."}` → `201` + `RepositoryResponse`.

### GET /api/v1/workspaces/{workspace_id}/repositories/tracked

Lists all repositories currently tracked in the workspace.
Requires `member` or `owner` role.

- Response: `[RepositorySummary]`.

### GET /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}

Returns details of a single tracked repository.
Requires `member` or `owner` role.

- Response: `RepositoryResponse`.

### DELETE /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}

Removes a repository from tracking (cascades pull requests).
Requires `owner` role.

- Response: `204 No Content`.

### POST /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync

Triggers synchronization of all pull requests from GitHub and idempotently upserts them into PostgreSQL.
Requires `owner` role.

- Response: `SyncResultResponse` (`repository_id`, `synced_count`, `status="completed"`).

### GET /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/pull-requests

Lists mirrored pull requests from local PostgreSQL storage with pagination and filtering.
Requires `member` or `owner` role.

- Query params: `state` (optional: `open`, `closed`, `all`), `page` (default 1), `per_page` (default 50, max 100).
- Response: `PullRequestListResponse` (`items`, `total`, `page`, `per_page`).

### POST /api/v1/webhooks/github

Receives GitHub webhook events with HMAC-SHA256 signature verification.
Unauthenticated by user token; verified via GitHub `X-Hub-Signature-256` header against `GITHUB_WEBHOOK_SECRET`.

- Headers: `X-GitHub-Event`, `X-Hub-Signature-256`.
- Supported events:
  - `ping`: responds with pong.
  - `pull_request` (`opened`, `closed`, `synchronize`, `reopened`, `edited`): mirrors PR changes to Neon DB in real-time.
- Response: `200 OK` + `{"status": "processed" | "pong" | "ignored", ...}`.

### GET /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/overview

Returns aggregated engineering metrics (Cycle Time p50/p90/avg, volume, merge rate) with resilient Redis cache-aside acceleration.
Requires `member` or `owner` role.

- Query params: `days` (default 30, min 1, max 365, or omitted for all-time).
- Response: `RepositoryMetricsResponse` (`total_prs`, `open_prs`, `merged_prs`, `closed_unmerged_prs`, `merge_rate_percentage`, `cycle_time`: `{"p50_hours", "p90_hours", "avg_hours"}`, `cached`: boolean).

### GET /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/throughput

Returns weekly merged pull request counts for velocity timelines.
Requires `member` or `owner` role.

- Query params: `weeks` (default 8, min 1, max 52).
- Response: `WeeklyThroughputResponse` (`weeks_analyzed`, `data`: `[{"week_start", "merged_count"}]`, `cached`: boolean).

### GET /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/authors

Returns contributor-level pull request activity and average cycle time breakdown.
Requires `member` or `owner` role.

- Query params: `days` (default 30).
- Response: `AuthorMetricsResponse` (`authors`: `[{"author_login", "total_prs", "merged_prs", "avg_cycle_time_hours"}]`, `cached`: boolean).

## Conventions

- JSON bodies validated with Pydantic schemas (`app/schemas/`).
- Thin handlers; services contain business logic; repositories access the DB.
- Errors use standard HTTP status codes.

