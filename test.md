I have completed a full inspection of the backend. **No files were modified** — this is a read-only audit (I ran only read-only enumeration, `git log`, `pytest`, and in-process `TestClient` probes).

---

# 🔍 BACKEND AUDIT — GitHub Engineering Intelligence (FastAPI)

**Repo:** `d:\practice-fastAPI\Github-dashboard` @ `430d2a0` (branch `main`)
**Audited:** `app/` (all 60 modules), `migrations/`, `docs/`, `tests/` (79 unit tests, all passing), `render.yaml`, `docker-compose.yml`, `Dockerfile`, `.env`, `requirements.txt`
**Route table enumerated at runtime** (`app.routes`) — this is the authoritative source, not `docs/api.md`.

> ⚠️ **The repo contains no frontend** (`Get-ChildItem -Recurse -Directory` found none). This is backend-only; your frontend is elsewhere. All base-URL/proxy decisions below are therefore documented, not verified.

---

# PHASE 1 — FULL BACKEND DISCOVERY

## 1.1 What actually exists

| Layer | Reality |
|---|---|
| `app/api/v1/` | **12 routers registered.** Only 4 are real: `me`, `workspaces`, `analytics`, `webhooks`. The other 8 (`github`, `repositories`, `issues`, `pull_requests`, `people`, `users`, `work`, `sync`) are **5-line empty `APIRouter` placeholders** with zero endpoints. |
| `app/services/` | 7 services, all real and wired. |
| `app/repositories/` | 6 repositories, all real. |
| `app/schemas/` | 7 schema modules — authoritative DTO definitions. |
| `app/models/` | 6 tables mirroring the 4 migrations. |
| `app/core/` | `config`, `database`, `redis`, `security`, `logging`. |
| `app/integrations/auth/` | `SupabaseTokenVerifier` (JWKS + RS256/ES256). |
| `app/integrations/github/` | `auth.py` (App JWT + installation tokens), `client.py` (REST), `webhooks.py` (HMAC). `commits.py`, `issues.py`, `releases.py`, `repositories.py`, `pull_requests.py` are **empty placeholders**. |
| `app/workers/` | `queue.py` (Redis LPUSH + in-process fallback), `worker.py` (BRPOP loop), `tasks/sync_task.py`. |
| `app/domain/` | **3 placeholder files, zero logic.** |
| `scripts/` | Empty (`.gitkeep` only). |
| Frontend-related | None. |

## 1.2 Authoritative route table (runtime-verified)

```
GET     /health                                                                    (public)
GET     /api/v1/me                                                                 (user)
POST    /api/v1/workspaces                                                         (user)
GET     /api/v1/workspaces                                                         (user)
GET     /api/v1/workspaces/{workspace_id}                                          (member)
GET     /api/v1/workspaces/{workspace_id}/github/install-url                       (OWNER)
POST    /api/v1/workspaces/{workspace_id}/github/connect                           (OWNER)
DELETE  /api/v1/workspaces/{workspace_id}/github/disconnect                        (OWNER)
GET     /api/v1/workspaces/{workspace_id}/github/repositories                      (member)
POST    /api/v1/workspaces/{workspace_id}/repositories/track                       (OWNER)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked                     (member)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}     (member)
DELETE  /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}     (OWNER)
POST    /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync (OWNER)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync-jobs/{job_id} (member)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync-jobs          (member)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/pull-requests     (member)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/overview        (member)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/throughput     (member)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/activity        (member)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/cycle-time-trend (member)
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/authors         (member)
POST    /api/v1/webhooks/github                                                    (GitHub HMAC)
```

Plus unauthenticated `/docs`, `/openapi.json`, `/redoc`.

## 1.3 Documentation-vs-implementation discrepancies

| # | Doc claim | Reality | Verdict |
|---|---|---|---|
| D1 | `docs/api.md:154,186` — overview/authors `days` "or omitted for **all time**" | `analytics.py:34` declares `days: int \| None = Query(30, ge=1, le=365)`. **Omitting it yields 30, not `None`.** Empirically: `""`→200/`days=30`; `?days=`→**422**; `?days=null`→**422**; `?days=0`→422; `?days=999`→422. **All-time is unreachable over HTTP.** | ❌ **DOC WRONG** |
| D2 | `docs/api.md:120` — sync-jobs status enum `queued/processing/completed/failed` | Schema is `status: str` (unconstrained). Values in code: the 4 above. No enum enforced. | ✅ accurate but unenforced |
| D3 | `docs/api.md` "All product endpoints except `/health` require a token" | True, **plus** `/api/v1/webhooks/github` needs its own HMAC (not a user token). Doc does say this at line 141. | ✅ |
| D4 | `docs/api.md:51` "Requires `owner` role" for install-url | ✅ `get_owned_workspace` | ✅ |
| D5 | `docs/architecture.md:30-31` "No business functionality is implemented yet" | **Stale** — 6 phases are implemented. | ❌ stale doc |
| D6 | `docs/database.md` lists only 3 tables | 6 tables exist (`repositories`, `pull_requests`, `sync_jobs` missing). | ❌ stale doc |
| D7 | `IMPLEMENTATION.md:53` "v1 resource routers (placeholders)" / `:142` `analytics`+`webhooks` are "empty placeholders" | Both are fully implemented. | ❌ stale doc |
| D8 | `docs/api.md:135` — `state` (`open`/`closed`/`all`) | No enum validation; any string is passed to SQL. `state=merged` → HTTP 200 + `{"items":[],"total":0}`. | ⚠️ undocumented behaviour |
| D9 | Docs never mention a 20-row cap on authors | `analytics_repository.py:335` `limit: int = 20`, not exposed by the route. | ⚠️ undocumented behaviour |
| D10 | Docs never mention `total_synced` semantics | It is `len(records)` = **PRs fetched & upserted this run**, not new PRs (`pull_request_repository.py:123`). | ⚠️ undocumented behaviour |
| D11 | Docs never mention the **5000-PR sync ceiling** | `client.py:242` `max_pages: int = 50` × 100/page. Silent truncation. | ⚠️ undocumented behaviour |
| D12 | Docs never mention `days` filters on **creation date** | overview + authors filter `PullRequest.github_created_at >= since` (`analytics_repository.py:129,356`), not merge date. | ⚠️ undocumented behaviour |

> Unrelated but relevant: `.env` **is committed to the repo** and contains live Neon/Supabase/GitHub credentials. Rotate them.

---

# PHASE 2 — COMPLETE API CONTRACT

**Universal facts**
- Base path: `/api/v1` (production app also exposes `/health`).
- All requests/responses are `application/json` unless noted.
- `workspace_id`, `repository_id`, `job_id` are **UUID path params**. A non-UUID value → **422** before any auth logic runs.
- Error shapes differ by source: `HTTPException` → `{"detail": "<string>"}`; Pydantic/FastAPI validation → `{"detail": [{"type","loc","msg","input","ctx?"}]}`. **The frontend must handle both.**

---

### A. Health

**`GET /health`** — no auth
- 200 → `{"status": "ok"}`

---

### B. Current user

**`GET /api/v1/me`** — Bearer token
Response 200 (`app/schemas/user.py:9`):
```json
{ "id": "<uuid>", "email": "string|null", "name": "string|null",
  "avatar_url": "string|null", "created_at": "<iso>", "updated_at": "<iso>" }
```
- **Side effect:** provisions the internal `User` on first call (`user_service.get_or_create_user`). Also silently syncs `email`/`name`/`avatar_url` from the token on every request.
- 401 `{"detail":"Not authenticated"}` / `"Invalid Authorization header"` / `"Invalid or expired token"`.

---

### C. Workspaces

**`POST /api/v1/workspaces`** — Bearer token, any authenticated user
- Body `WorkspaceCreate`: `{ "name": string }` — `min_length=1, max_length=255`. Violation → 422.
- Success **201** (`WorkspaceResponse`):
```json
{ "id":"<uuid>","name":"string","github_installation_id":null,
  "created_at":"<iso>","updated_at":"<iso>","is_github_connected":false }
```
- `is_github_connected` is a **computed field** (not a DB column), derived as `github_installation_id !== null`.
- Caller becomes `owner` atomically. No other error paths.

**`GET /api/v1/workspaces`** — Bearer token
- Success 200 → **bare array** of `WorkspaceSummary`:
```json
[{ "id":"<uuid>","name":"string","github_installation_id":null,"created_at":"<iso>" }]
```
- ⚠️ **`WorkspaceSummary` has NO `is_github_connected`** (only `WorkspaceResponse` does). Ordered by `created_at ASC`. No pagination.
- 401 if unauthenticated. Empty array if no memberships.

**`GET /api/v1/workspaces/{workspace_id}`** — Bearer token + **member**
- 200 → `WorkspaceResponse` (same shape as create, with real `is_github_connected`).
- **404** `{"detail":"Workspace not found"}` if the row does not exist.
- **403** `{"detail":"You do not have access to this workspace"}` if it exists but the caller is not a member.

---

### D. GitHub connection

**`GET /api/v1/workspaces/{workspace_id}/github/install-url`** — Bearer + **OWNER**
- 200 → `{ "install_url": "https://github.com/apps/<slug>/installations/new?state=<workspace_id>" }`
- **500** `{"detail":"GitHub App is not configured on the server"}` if `GITHUB_APP_SLUG` is unset (`GitHubAppConfigError`).
- 404 / 403 per workspace resolution. `state` is the raw `workspace_id` string — **never validated anywhere in this codebase.**

**`POST /api/v1/workspaces/{workspace_id}/github/connect`** — Bearer + **OWNER**
- Body `GitHubConnectRequest`: `{ "installation_id": int }` — **`gt=0`**, violation → 422.
- Behaviour: calls GitHub `GET /installation/repositories?per_page=1` with an App installation token **before** persisting. Then writes `workspaces.github_installation_id`.
- Success **200** → `WorkspaceResponse` with `github_installation_id` set, `is_github_connected: true`.
- **400** `{"detail":"Unable to verify GitHub installation: <msg>"}` — for `GitHubAuthError` **and** `GitHubNotFoundError` (a missing installation surfaces as 400, not 404).
- ⚠️ **Unhandled → 500**: `GitHubRateLimitError`, `GitHubAPIError`, `GitHubAppConfigError`, and `IntegrityError` if that `installation_id` is already linked to another workspace (column is **globally UNIQUE**). See L6, L7.
- 404/403 per workspace resolution.

**`DELETE /api/v1/workspaces/{workspace_id}/github/disconnect`** — Bearer + **OWNER**
- No body. Sets `github_installation_id = NULL`. Does **not** delete tracked repositories or PRs.
- Success 200 → `WorkspaceResponse` with `is_github_connected: false`.
- 404/403 per workspace resolution. Idempotent.

**`GET /api/v1/workspaces/{workspace_id}/github/repositories`** — Bearer + **member**
- Query: `page` (int, ≥1, default **1**), `per_page` (int, **1–100**, default **100**). Violations → 422.
- Success 200 → **bare array** of `GitHubRepositoryResponse`:
```json
[{ "github_id":123,"node_id":"R_kgDO...","name":"repo","full_name":"org/repo",
   "private":true,"html_url":"https://github.com/org/repo",
   "default_branch":"main","description":"string|null" }]
```
- ⚠️ **No envelope, no `total_count`, no `has_more`.** GitHub returns up to 100; the frontend must page until `items.length < per_page`.
- **400** `{"detail":"Workspace is not connected to GitHub"}` (GitHub not connected).
- **429** `{"detail":"GitHub rate limit exceeded. Resets at: <epoch|null>"}`.
- **502** `{"detail":"GitHub authentication error: <msg>"}`.
- ⚠️ `GitHubAPIError` (any other non-2xx, incl. secondary rate limits) is **unhandled → 500**.

---

### E. Repositories

**`POST /api/v1/workspaces/{workspace_id}/repositories/track`** — Bearer + **OWNER**
- Body `RepositoryTrackRequest`: `{ "owner": string, "repo": string }` — each `min_length=1, max_length=255`. Violation → 422.
- Behaviour: `GET /repos/{owner}/{repo}` via the installation token, then **upsert** (idempotent). Re-tracking an existing repo refreshes metadata and sets `is_tracked = true`.
- Success **201** → `RepositoryResponse`:
```json
{ "id":"<uuid>","workspace_id":"<uuid>","github_id":123,"node_id":"R_...",
  "name":"repo","full_name":"org/repo","owner_login":"org","private":false,
  "html_url":"https://github.com/org/repo","default_branch":"main",
  "description":"string|null","is_tracked":true,
  "created_at":"<iso>","updated_at":"<iso>" }
```
- **400** `"Workspace is not connected to GitHub"` (workspace has no installation).
- **404** `{"detail":"GitHub repository <owner>/<repo> not found"}`.
- **429** / **502** as above. ⚠️ `GitHubAPIError` → **500**.
- ⚠️ Does **not** enqueue a sync. Analytics will be all-zero until sync is called.

**`GET /api/v1/workspaces/{workspace_id}/repositories/tracked`** — Bearer + **member**
- 200 → **bare array** of `RepositorySummary` (ordered `name ASC`, no pagination):
```json
[{ "id":"<uuid>","name":"repo","full_name":"org/repo","private":false,
   "is_tracked":true,"html_url":"https://github.com/org/repo","default_branch":"main" }]
```
- ⚠️ **No `github_id`, no `workspace_id`, no `owner_login`, no timestamps.** To reconcile against the GitHub listing you must join on `full_name`.

**`GET /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}`** — Bearer + **member**
- 200 → `RepositoryResponse` (full shape above, incl. `github_id`).
- **404** `{"detail":"Repository not found in this workspace"}` — covers both "does not exist" and "belongs to a different workspace" (no leak).

**`DELETE /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}`** — Bearer + **OWNER**
- Success **204 No Content** — **empty body**. Do not attempt `res.json()`.
- **404** as above. Cascades delete `pull_requests` and `sync_jobs` (FK `ON DELETE CASCADE`).

---

### F. Sync

**`POST /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync`** — Bearer + **OWNER**
- No body.
- Success **202** → `SyncJobCreateResponse`:
```json
{ "job_id":"<uuid>", "status":"queued", "message":"Synchronization task enqueued successfully" }
```
- **400** `"Workspace is not connected to GitHub"` (checked first).
- **404** `"Repository not found in this workspace"`.
- Order of operations (`workspaces.py:291-303`): create `SyncJob(status="queued")` → **commit** → `LPUSH` to Redis (`github_intel:queue:sync_jobs`) → return 202.
- ⚠️ If Redis is down, it falls back to `asyncio.create_task(run_sync_job(...))` **in-process** and still returns `status: "queued"` (L11).
- ⚠️ **No dedup guard** — repeat calls create independent jobs that all run a full sync concurrently (L10).

**`GET /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync-jobs/{job_id}`** — Bearer + **member**
- 200 → `SyncJobResponse`:
```json
{ "id":"<uuid>","workspace_id":"<uuid>","repository_id":"<uuid>",
  "status":"queued|processing|completed|failed",
  "total_synced":0,"error_message":"string|null",
  "started_at":"<iso>|null","completed_at":"<iso>|null",
  "created_at":"<iso>","updated_at":"<iso>" }
```
- **404** if the repository isn't in this workspace, **or** `{"detail":"Sync job not found"}` if the job is missing/mismatched.

**`GET /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync-jobs`** — Bearer + **member**
- Query `limit` (int, **1–50**, default **10**). Violation → 422.
- 200 → **bare array** of `SyncJobResponse`, sorted `created_at DESC`.
- 404 if repository not in workspace.
- ⚠️ The repo-existence check runs **before** the query, so the empty array is only reachable for a valid repo with no jobs.

**Pull requests:** `GET .../pull-requests` — Bearer + member
- Query: `state` (string|null, **unvalidated**), `page` (≥1, default 1), `per_page` (**1–100**, default **50**).
- 200 → `PullRequestListResponse`:
```json
{ "items":[ { "id":"<uuid>","repository_id":"<uuid>","github_id":1,"node_id":"PR_...",
  "number":1,"title":"...","state":"open|closed","draft":false,
  "author_login":"string|null","html_url":"...","merged_at":"<iso>|null",
  "closed_at":"<iso>|null","github_created_at":"<iso>","github_updated_at":"<iso>",
  "created_at":"<iso>","updated_at":"<iso>" } ],
  "total": 1, "page": 1, "per_page": 50 }
```
- Sorted `number DESC`. `total` respects the `state` filter.
- ⚠️ `state` is compared literally to `pull_requests.state`, whose domain is **only `open`/`closed`** (GitHub never returns `merged`). `state=merged` → 200 with an empty list.
- ⚠️ `state=""` → treated as a real filter (`state is not None and state != "all"`) → returns 0 rows. Always omit the param rather than sending an empty string.
- 404 if repository not in workspace.

---

### G. Analytics (all Bearer + **member**, all `200`)

| Endpoint suffix | Query | Default | Range | Response |
|---|---|---|---|---|
| `/analytics/overview` | `days` | **30** | 1–365 | `RepositoryMetricsResponse` |
| `/analytics/throughput` | `weeks` | **8** | 1–52 | `WeeklyThroughputResponse` |
| `/analytics/activity` | `days` | **30** | 1–365 | `ActivityTrendResponse` |
| `/analytics/cycle-time-trend` | `weeks` | **12** | 1–52 | `CycleTimeTrendResponse` |
| `/analytics/authors` | `days` | **30** | 1–365 | `AuthorMetricsResponse` |

Exact shapes (`app/schemas/analytics.py`):

```jsonc
// overview
{ "repository_id":"<uuid>", "time_window_days":30,
  "total_prs":0,"open_prs":0,"merged_prs":0,"closed_unmerged_prs":0,
  "merge_rate_percentage":null,             // float|null
  "cycle_time":{"p50_hours":null,"p90_hours":null,"avg_hours":null},
  "cached":false }

// throughput
{ "repository_id":"<uuid>","weeks_analyzed":8,
  "data":[{"week_start":"2026-09-14T00:00:00","merged_count":0,"is_partial":false}],
  "cached":false }

// activity
{ "repository_id":"<uuid>","days_analyzed":30,
  "data":[{"day":"2026-09-20T00:00:00","created_count":0,"merged_count":0}],
  "cached":false }                          // NOTE: no is_partial

// cycle-time-trend
{ "repository_id":"<uuid>","weeks_analyzed":12,
  "data":[{"week_start":"...","p50_hours":null,"p90_hours":null,"avg_hours":null,"is_partial":true}],
  "cached":false }

// authors
{ "repository_id":"<uuid>","time_window_days":30,
  "authors":[{"author_login":"a","total_prs":1,"merged_prs":1,"avg_cycle_time_hours":null}],
  "cached":false }
```

- **404** `{"detail":"Repository not found in this workspace"}` on every analytics endpoint (access is checked **before** the cache lookup, so no cross-tenant cache leak).
- All other errors → 422 (bad query) or 401.
- **Cache:** keyed `analytics:{overview|throughput|activity|cycletime|authors}:{repository_id}:{days|weeks}:{value}`, TTL **900 s**, `cached: true` on hits. Cache is **not** consulted for any other endpoint.

---

### H. Webhook

**`POST /api/v1/webhooks/github`** — GitHub HMAC, **not** a user token
- Required header `X-GitHub-Event` (**missing → 422**, because it's `Header(...)`).
- Optional `X-Hub-Signature-256: sha256=<hex>`.
- If `GITHUB_WEBHOOK_SECRET` is set: invalid/missing signature → **401** `{"detail":"Invalid or missing webhook signature"}`.
- ⚠️ If `GITHUB_WEBHOOK_SECRET` is **empty/None**, verification is **skipped entirely** (`webhooks.py:31`) — see L5.
- Malformed JSON → **400** `{"detail":"Malformed JSON payload"}`.
- 200 bodies (`app/services/webhook_service.py`):
  - `ping` → `{"status":"pong","zen":"..."}`
  - `pull_request`, repo tracked → `{"status":"processed","action":"opened","pr_number":12,"matched_repositories":1}`
  - `pull_request`, repo **not** tracked → `{"status":"ignored","reason":"repository_not_tracked"}`
  - `pull_request`, missing PR/repo in payload → `{"status":"ignored","reason":"missing_pull_request_or_repository"}`
  - any other event (`issues`, `push`, `installation`, …) → `{"status":"ignored","event":"<name>"}`

---

# PHASE 3 — AUTHENTICATION FLOW (verified in code)

```
Request → Authorization header → _extract_bearer_token() → verifier.verify()
        → SupabaseTokenVerifier._verify_sync() (JWKS, RS256/ES256)
        → VerifiedIdentity → user_service.get_or_create_user() → User
```

**Header format:** `Authorization: Bearer <supabase-access-token>`. Scheme comparison is case-insensitive (`scheme.lower() != "bearer"`), so `bearer` works too.

**Token source:** the Supabase JS client session access token (`session.access_token`). No endpoint issues or refreshes tokens — the backend only verifies.

**Verification specifics** (`integrations/auth/verifier.py:56-85`):
- Signing key resolved by `kid` from `SUPABASE_JWKS_URL`; JWKS fetch is offloaded via `asyncio.to_thread`.
- `algorithms=["RS256","ES256"]`, `audience=SUPABASE_JWT_AUDIENCE` (default `"authenticated"`), `issuer=SUPABASE_JWT_ISSUER`.
- `options={"require": ["sub","exp","iss"]}`.
- Claims → identity: `sub` → `external_user_id`; `email`; `name` ← `user_metadata.full_name ?? user_metadata.name`; `avatar_url` ← `user_metadata.avatar_url ?? user_metadata.picture`.

**Failure matrix (empirically verified):**

| Condition | Status | Body |
|---|---|---|
| No `Authorization` header | 401 | `{"detail":"Not authenticated"}` + `WWW-Authenticate: Bearer` |
| `Basic ...`, `Bearer` (no token), any non-bearer scheme | 401 | `{"detail":"Invalid Authorization header"}` |
| Malformed signature / expired / wrong iss / wrong aud / unknown kid / unknown `sub` | 401 | `{"detail":"Invalid or expired token"}` |
| **Supabase env unset** (`JWKS_URL` or `ISSUER` missing) | **500** ⚠️ | unhandled `TokenVerificationError` (L8) |

**Internal user resolution:** resolved on **every request** from `auth_provider_user_id` (unique). Created on first request; `email`/`name`/`avatar_url` are overwritten if the token differs. Concurrent first requests are safe (unique constraint + `IntegrityError` recovery with re-read).

**Membership / role checks:**
- `get_accessible_workspace` → `workspace_service.get_workspace_for_member` → membership row exists (any role). Missing workspace → 404; non-member → 403.
- `get_owned_workspace` → membership row exists **and** `role == "owner"`. Missing → 404; non-owner (incl. plain `member`) → **403 `{"detail":"Owner permissions required for this action"}`**.

**Owner-only:** `github/install-url`, `github/connect`, `github/disconnect`, `repositories/track`, `repositories/tracked/{id}` DELETE, `.../sync`.
**Member-or-owner:** `workspaces/{id}` GET, `github/repositories`, `repositories/tracked` GET, `repositories/tracked/{id}` GET, `sync-jobs` GET×2, `pull-requests`, all 5 analytics.

**Token refresh:** yes — Supabase must auto-refresh; on 401 `"Invalid or expired token"` the frontend should refresh then retry **once**.

**Edge cases the frontend must handle:**
1. **403 "Owner permissions required" is the only signal of role.** No endpoint returns the caller's role (L1 — Critical).
2. 401 has **three distinct `detail` strings**; only `"Invalid or expired token"` is refresh-worthy. `"Not authenticated"` means no session; `"Invalid Authorization header"` usually means a malformed header (e.g. missing space, or `Token` instead of `Bearer`).
3. A 404 on a workspace means "never existed"; a 403 means "exists but forbidden". Do not conflate.
4. 422 responses have `detail` as an **array**, not a string.
5. Clock skew: `exp` is enforced by PyJWT with default leeway (0 s). Refresh proactively.
6. There is **no logout/revocation** endpoint and no server-side session — logout is purely client-side.
7. **No endpoint returns workspace members** (`/users`, `/people` are empty) — the frontend cannot build a member list or invite flow.

---

# PHASE 4 — WORKSPACE + GITHUB CONNECTION FLOW

| Step | Endpoint | Role | Response | IDs the frontend must keep |
|---|---|---|---|---|
| 1. Sign in | Supabase client | — | session | `access_token` |
| 2. List/create workspace | `GET /workspaces` / `POST /workspaces` | user | `WorkspaceSummary[]` / `WorkspaceResponse` | **`workspace_id`** |
| 3. Read workspace detail | `GET /workspaces/{id}` | member | `WorkspaceResponse` | `github_installation_id`, `is_github_connected` |
| 4. Request install URL | `GET /workspaces/{id}/github/install-url` | **OWNER** | `{install_url}` | — |
| 5. Redirect user | browser → `install_url` | — | GitHub install UI | — |
| 6. GitHub redirects back | **your frontend's Setup URL** | — | `?installation_id=…&setup_action=install&state=<workspace_id>` | `installation_id`, `state` |
| 7. Confirm connection | `POST /workspaces/{id}/github/connect` `{installation_id}` | **OWNER** | `WorkspaceResponse` (`is_github_connected: true`) | — |
| 8. List installable repos | `GET /workspaces/{id}/github/repositories` | member | `GitHubRepositoryResponse[]` | `owner`+`name` for track |
| 9. Track a repo | `POST /workspaces/{id}/repositories/track` `{owner,repo}` | **OWNER** | `RepositoryResponse` (`201`) | **`repository_id`** |
| 10. Trigger sync | `POST .../tracked/{repository_id}/sync` | **OWNER** | `202 {job_id}` | **`job_id`** |
| 11. Poll | `GET .../sync-jobs/{job_id}` | member | `SyncJobResponse` | terminal = `completed`/`failed` |
| 12. Read analytics | 5 analytics endpoints | member | analytics shapes | — |

**"Is GitHub connected?"** → `WorkspaceResponse.is_github_connected` (or `github_installation_id !== null`). `WorkspaceSummary` only exposes `github_installation_id` — recompute it in the list view.

**"Is a repo tracked?"** → cross-reference `GET .../repositories/tracked` against `GET .../github/repositories` **on `full_name`** (the available join key). For the tracked side you then need `id` (the UUID) for all subsequent calls; `github_id` is only in the *detail* response.

**Errors by step**
- 4 → 500 if `GITHUB_APP_SLUG` unset. 403 if not owner.
- 6 → **NOT VERIFIED IN CODEBASE.** There is no backend callback route. The redirect lands wherever the GitHub App's **Setup URL** is configured in GitHub's UI — invisible to this repo. If it points at the frontend, the frontend must parse `installation_id`/`state`; if it points at the backend, nothing handles it (the backend has no such route).
- 7 → 400 (bad/unverifiable installation), **500 on rate limit / API error / already-linked installation** (L6, L7).
- 8 → 400 not connected, 429 rate limit, 502 auth, **500 otherwise**.
- 9 → 400 not connected, 404 repo not visible to the installation, 429/502, **500 otherwise**.

**Frontend state to store:** `access_token`, `workspace_id`, `github_installation_id`, `repository_id`, `job_id`, and a flag for "pending install" (set before redirecting to GitHub; cleared after step 7 — survive it across a full-page navigation via `sessionStorage`).

**Notable gaps:** uninstalling the GitHub App on GitHub's side emits `installation`/`installation_repositories` events, which the backend **ignores** (`webhook_service.py:51`) — `is_github_connected` will stay `true` and repo listing will start failing. Manual disconnect is the only recovery.

---

# PHASE 5 — REPOSITORY + SYNC FLOW

```
track (201, repository_id)
  → POST /sync (202, job_id; DB row inserted & COMMITTED, then LPUSH)
    → worker BRPOPs → status=processing (+started_at, committed)
      → fetch_all_pull_requests (GitHub, ≤50 pages × 100)
        → upsert_batch (INSERT … ON CONFLICT (repository_id, number) DO UPDATE)
          → invalidate_repository_cache(repository_id)   ⚠️ BEFORE COMMIT
            → status=completed (+total_synced, completed_at)
              → analytics recomputed on next GET (cached:false), then cached 900 s
   failure path → rollback → status=failed (+error_message, completed_at)
```

**Triggering:** `POST .../sync` with no body. Only **owners**.

**Polling:** `GET .../sync-jobs/{job_id}` — a single indexed row read. Recommended: **2 s for the first 15 s, then 5 s, cap ~120 s**, then surface a "still queued — worker may be unavailable" state and offer a manual refresh. Rationale: a full sync is 1–50 GitHub calls; typical completion is a few seconds, but nothing in the contract bounds it.

**Terminal states:** `completed`, `failed`. `queued` and `processing` are non-terminal. ⚠️ **Nothing guarantees a `queued` job ever leaves that state** — see L2 (Critical).

**`total_synced` semantics (verified):** = `len(records)` passed to `ON CONFLICT` (`pull_request_repository.py:70-123`) = **number of PRs fetched from GitHub and upserted in this run**. It is *not* the count of newly created rows, *not* the count of changed rows, and it is **capped at 5000** (`max_pages=50`, `per_page=100`). Re-running a sync on unchanged data reports the same number. Label it in the UI as **"PRs processed"**, never "new PRs".

**Error handling:** `error_message` carries the raw exception string. Realistic values:
- `"GitHub API rate limit exceeded"` (from `GitHubRateLimitError`) — 403 + `"rate limit"` in body only.
- `"Failed to obtain installation token (status N): …"`
- `"GitHub resource not found: /repos/…"` (repo deleted/renamed after tracking)
- `"Network error during GitHub API request: …"`

**Triggering sync twice:** independent jobs, independent full syncs, concurrently, no locking (L10). Result: duplicated GitHub API consumption, concurrent upserts of the same rows (possible lock waits), and multiple cache invalidations. The frontend should **disable the button while an active job exists** — poll `GET .../sync-jobs?limit=1` first.

**Rate limits:** reliable for *primary* limits (403 + `"rate limit"`), unreliable for *secondary* limits (`403 …"secondary rate limit"…` or `429`) — those become `GitHubAPIError`, i.e. a **500** on `track`/`connect` and a raw string inside `error_message` for sync (L4).

**Race conditions / stale state relevant to the frontend**
1. **Cache invalidated before commit** (`sync_service.py:95` precedes `sync_task.py:41`'s commit) — a concurrent analytics read can repopulate the cache from pre-sync data for 900 s (L3, High).
2. **`queued` forever** if no worker process consumes Redis (L2, Critical).
3. **In-process fallback tasks are fire-and-forget** (`queue.py:55`) with no strong reference (L11).
4. **The job row is committed before `LPUSH`** — a crash between them leaves a permanently `queued` row.
5. `untrack` (DELETE) cascades `sync_jobs`, so a job being polled can vanish → **404**. The frontend must tolerate a 404 mid-poll.

---

# PHASE 6 — WEBHOOK + DATA FRESHNESS

**Pipeline**
```
GitHub → POST /api/v1/webhooks/github
  → X-GitHub-Event required (else 422)
  → if GITHUB_WEBHOOK_SECRET set: HMAC-SHA256 over the raw body, constant-time compare
      (git push 401 otherwise; secret unset ⇒ verification SKIPPED)
  → json.loads (400 on malformed)
  → webhook_service.process_github_event
      ping          → {"status":"pong"}
      pull_request  → _handle_pull_request_event
      anything else → {"status":"ignored"}
  → _handle_pull_request_event:
      repository.id (GitHub numeric id) → repository_repo.list_by_github_id(is_tracked=True)
          none → ignored / repository_not_tracked
      GitHubPullRequestData.from_api_payload (raises GitHubAPIError if created_at/updated_at missing)
      for EACH matching repo across ALL workspaces:
          pull_request_repo.upsert_batch(...)        # ON CONFLICT (repository_id, number) DO UPDATE
          analytics.invalidate_repository_cache(repo.id)
  → get_db commits AFTER the handler returns
```

**Supported events:** `ping` and `pull_request` **only**. Within `pull_request`, the `action` is not filtered — `opened`, `closed`, `reopened`, `synchronize`, `edited`, `labeled`, … all take the same path and are treated identically (the whole PR object is mirrored).

**What changes per event:** `title`, `state`, `draft`, `author_login`, `html_url`, `merged_at`, `closed_at`, `github_updated_at`, `updated_at`. `github_id`, `node_id`, `number`, `github_created_at`, `repository_id`, `created_at` are **not** overwritten on conflict.

**Synchronous or asynchronous?** **Synchronous** — the DB write happens inside the HTTP request, before the 200 is returned. No queue. GitHub's 10 s delivery timeout applies.

**Failure handling:** any exception inside `upsert_batch` propagates → FastAPI 500 → GitHub marks the delivery failed and may retry. There is **no retry/backoff/dead-letter** of our own, and no delivery-id dedupe (unnecessary: the upsert is idempotent).

**Cache invalidation — verified line by line** (`analytics_service.py:232-238`):

| Cache | Invalidated? | Evidence |
|---|---|---|
| `analytics:overview:{repo}` | ✅ | line 234 + `test_analytics.py:431-451` asserts the exact ordered list |
| `analytics:throughput:{repo}` | ✅ | line 235 |
| `analytics:authors:{repo}` | ✅ | line 236 |
| `analytics:activity:{repo}` | ✅ | line 237 |
| `analytics:cycletime:{repo}` | ✅ | line 238 |

All 5 prefixes are deleted with `SCAN`+`DEL` on `prefix*`, which matches every `days`/`weeks` variant. **No missing invalidation.** The only defect is *ordering* (before commit, L3).

**What the frontend should expect after a webhook:** the *next* analytics request for the affected repository recomputes from the DB and returns `cached: false`. Previously-fetched chart data is already in TanStack Query state and will **not** change on its own — the frontend must refetch (or poll).

**Polling/refetching:** GitHub delivers webhooks for **tracked, connected** repositories, but delivery is best-effort (retries, drops, delays) and the pipeline is **eventually consistent** with no push channel to the browser. Recommend: refetch analytics on window focus + a light 60–120 s background interval while a dashboard is visible. Do **not** rely on webhooks for freshness in the UI.

**Cache-thrash note:** every single webhook event deletes all 5 keys for the repo. On a busy repo (many `synchronize`/`labeled` events) the analytics cache is effectively never warm. Correctness is preserved; latency increases. Low severity, worth knowing when tuning `staleTime`.

---

# PHASE 7 — ANALYTICS AUDIT (route → service → Redis → repository → SQL)

All five follow the identical shape: **`_verify_repository_access` → cache read → SQL → build response → cache write (TTL 900) → return**. Access is verified *before* the cache read — good.

### 7.1 OVERVIEW — `RepositoryMetricsResponse`
Repository: `get_overview_metrics` (`analytics_repository.py:97-161`). SQL: one aggregate query, `WHERE repository_id = :id` `[AND github_created_at >= now() - days]`.

| Field | SQL | Exact meaning |
|---|---|---|
| `total_prs` | `count(id)` | All mirrored PRs in the window (by **creation** date), any state. |
| `open_prs` | `count(case state='open')` | `state` is literally `'open'`. |
| `merged_prs` | `count(case merged_at IS NOT NULL)` | Merge happens regardless of `state`. |
| `closed_unmerged_prs` | `count(case state='closed' AND merged_at IS NULL)` | Closed without merging. |
| `merge_rate_percentage` | `round(merged / (merged + closed_unmerged) * 100, 1)` | **`None` if the denominator is 0.** Open PRs are excluded from the denominator. |
| `cycle_time.p50_hours` | `percentile_cont(0.50) within_group(extract(epoch, merged_at - github_created_at)/3600)` | Continuous (interpolated) median of **merge-duration in hours**. NULL durations (open PRs) are ignored by the ordered-set aggregate. `None` if no merged PRs. Rounded to 2 dp. |
| `cycle_time.p90_hours` | same, `0.90` | 90th percentile. |
| `cycle_time.avg_hours` | `avg(case(merged_at IS NOT NULL, duration))` | Mean over **merged** PRs only. |

⚠️ **Cycle time = `merged_at − github_created_at`**, i.e. *total* time from PR creation to merge (not "first commit → merge", not "review time", not "open → merge"). Nothing else is stored.
⚠️ **`p50`/`p90` are computed over rows matching the WHERE clause, which is filtered by creation date but *not* by merge date** — a PR created inside the window and merged 6 months later contributes a huge duration. Mixed windowing semantics.

### 7.2 THROUGHPUT — `WeeklyThroughputResponse`
`get_weekly_throughput` (`:163-206`), helpers `week_bucket_starts` (`:13-23`) + `fill_week_counts` (`:42-54`).
- **Window:** `weeks` Monday-aligned buckets ending with the current (in-progress) week's Monday. `weeks=8` ⇒ 8 items, indices `[0..7]`, `starts[0] = monday − 7 weeks`, `starts[7] = this Monday`. **Always exactly `weeks` items** (`weeks_analyzed` echoes the request).
- **Week definition:** PostgreSQL `date_trunc('week', timezone('UTC', merged_at))` — **Monday 00:00 UTC**, `[Mon, Sun]`, inclusive of the start, exclusive of the next Monday.
- **Merge definition:** `merged_at IS NOT NULL` **and** `merged_at >= starts[0]` (as an aware UTC timestamp). There is **no upper bound** — a future-dated `merged_at` lands in a bucket absent from `starts` and is silently discarded.
- **Zero filling:** ✅ every bucket present; missing → `merged_count: 0`. Verified by `test_fill_week_counts_zero_fills_and_marks_partial`.
- **Partial week:** ✅ `is_partial: true` **on the last item only** (index `len-1`), i.e. always the current week.
- **Timezone:** all bucketing is UTC. Bucket keys are naive UTC datetimes, normalised by `_bucket_key` for dict lookup — correct.
- **Boundary:** a merge at exactly `00:00:00` Monday UTC belongs to the *new* week; at `23:59:59.999` Sunday to the old one.

### 7.3 ACTIVITY — `ActivityTrendResponse`
`get_daily_activity` (`:208-268`), helpers `day_bucket_starts` (`:26-30`) + `fill_day_counts` (`:57-70`).
- **Window:** `days` consecutive **UTC midnight** buckets, ending with **today**. `days=30` ⇒ 30 items, `starts[0] = today − 29d`, `starts[29] = today 00:00 UTC`. Always exactly `days` items.
- **`created_count`:** PRs whose `github_created_at` falls in that UTC day. **Includes PRs of every state** (open, closed, merged).
- **`merged_count`:** PRs whose `merged_at` falls in that UTC day (`merged_at IS NOT NULL`).
- **Day boundaries:** `date_trunc('day', timezone('UTC', col))` — **00:00–23:59:59.999 UTC**.
- **Zero filling:** ✅ both series.
- ⚠️ **No `is_partial` field.** The last bucket is *always* today and therefore always incomplete — both counts are partial for the current day. Inconsistent with throughput/cycle-time-trend, which do flag it.
- ⚠️ The two series use **different time bases** (creation vs merge), so a PR appears under `created_count` on its creation day and under `merged_count` on its merge day. That is intended for this chart, but the frontend must not sum them into a single "activity" number.
- Two separate SQL queries are issued per request (created, merged) — not a single query with two filtered aggregates.

### 7.4 CYCLE-TIME TREND — `CycleTimeTrendResponse`
`get_cycle_time_trend` (`:270-327`) + `fill_week_percentiles` (`:73-91`).
- **Cycle-time definition:** identical to overview — `merged_at − github_created_at`, in hours.
- **Bucketing:** by **merge date** (`date_trunc('week', timezone('UTC', merged_at))`) — the opposite of overview's creation-date window.
- **Window:** `weeks` Monday buckets, oldest first, last = current week. Always exactly `weeks` items.
- **`p50_hours` / `p90_hours`:** `percentile_cont(0.50/0.90) within_group(duration_hours)`, rounded to 2 dp, computed per week.
- **`avg_hours`:** `avg(duration_hours)` per week.
- **No merges in a week ⇒ `None`, not 0** for all three fields — deliberate, documented in the docstring and asserted by `test_fill_week_percentiles_preserves_empty_week_gaps`. Charts must render **gaps**, not zeros.
- **Partial week:** ✅ `is_partial: true` on the last item only.
- "No merges at all" ⇒ every item has three `None`s and the series is length `weeks`.
- `weeks=1` ⇒ a single bucket covering the current week, `is_partial: true`.

### 7.5 AUTHORS — `AuthorMetricsResponse`
`get_author_metrics` (`:329-375`).
- **Author identification:** `pull_requests.author_login` — the **GitHub login string** (≤255 chars), derived from the PR payload's `user.login`. There is **no author table, no stable author ID, no avatar, no email**. GitHub logins can be renamed and there is no relinking.
- **`total_prs`:** all PRs by that author in the window (creation-date filtered), any state.
- **`merged_prs`:** `count(case merged_at IS NOT NULL)` by that author.
- **`avg_cycle_time_hours`:** mean merge-duration over that author's **merged** PRs; `None` if none merged. Rounded to 2 dp. Note it is an **average only — no p50/p90 per author**.
- **Time window:** `days` filters on **`github_created_at`** (creation, like overview). Default 30, range 1–365, and the same unreachable-`None` defect.
- ⚠️ Rows with `author_login IS NULL` are **excluded entirely**. Authors whose logins are null (deleted accounts, some ghost users) vanish from the report.
- ⚠️ **`LIMIT 20`, hard-coded** (`limit: int = 20`), ordered `count(id) DESC`. Only the **top 20 authors by total PRs** are ever returned; no tie-break, no stable secondary sort, no total, no pagination, and the limit is not exposed as a query param. A 21-author repo silently loses data.
- No `RepositoryNotFoundError` risk beyond the shared access check.

### 7.6 Cache behaviour (all 5)
- Key: `analytics:{overview|throughput|activity|cycletime|authors}:{repository_id}:{days|weeks}:{value}`.
- TTL: **900 s**, no jitter, no versioning.
- Miss → compute → `SET` with TTL. `cached: false`.
- Hit → `model_validate_json` → force `cached = true` → return. **Redis is not re-queried for TTL extension.**
- Redis down → `get` returns `None`, `set` returns `False` (logged warning) — **every request is a cache miss and still returns 200**. Verified by `test_redis_soft_fail_on_connection_error`.
- **The frontend cannot force a bypass.** `days`/`weeks` are the only parameters and both are part of the key, so no query-string trick produces a fresh computation. The only invalidation paths are sync completion and webhook handling.
- A `cached: true` response may be up to 15 minutes old **and** (due to L3) may predate the latest sync.

---

# PHASE 8 — DATA-CORRECTNESS LOOPHOLES

Severity: **C**ritical / **H**igh / **M**edium / **L**ow.

---

**L1 — Frontend cannot determine the caller's role. Severity: CRITICAL**
`app/schemas/workspace.py:15-40`, `app/repositories/workspace_repository.py`. `WorkspaceResponse`/`WorkspaceSummary` expose no `role`; `UserResponse` has none; there is no members endpoint (`users.py`, `people.py` are empty routers); `workspace_members` is never read for output.
*Why it's a problem:* 6 endpoints are owner-only. The UI cannot decide whether to render/enable the install, connect, disconnect, track, untrack, and sync controls, and cannot show a role badge.
*Example:* a `member` loads the dashboard → all controls are hidden/broken, but the frontend has no data to know that.
*Frontend impact:* either an unavoidable 403 on first click, or a probe hack.
*Backend fix:* add `role` to `WorkspaceResponse` (and `WorkspaceSummary`) in `get_workspace_for_member`. **Small change, large payoff.**
*Frontend workaround:* probe `GET .../github/install-url` once per workspace and cache `403 ⇒ member`. Works but generates a 403 in the logs and is fragile.
*Fix before integration?* **Yes.**

---

**L2 — Sync jobs never complete in the deployed environment (no worker process). Severity: CRITICAL**
`render.yaml:6` (`startCommand: uvicorn app.main:app …`), `docker-compose.yml:15` (same), `Dockerfile` CMD (same), `app/main.py:19-24` (lifespan only configures logging/disposes the engine). `python -m app.workers.worker` appears **nowhere** in any deployment artefact. `REDIS_URL` **is** configured in production (`render.yaml`), so `enqueue_sync_job` succeeds via `lpush` and **never** takes the in-process fallback.
*Why it's a problem:* `POST /sync` returns 202 with a `job_id`, and that job stays `queued` **forever**.
*Example:* the frontend polls `/sync-jobs/{id}` indefinitely; analytics stay empty; the user concludes the product is broken.
*Frontend impact:* **blocking.** Every sync-dependent flow (analytics, PR list) is dead in production.
*Backend fix:* add a Render background-worker service (`startCommand: python -m app.workers.worker`) and a `worker` service to `docker-compose.yml`, sharing `REDIS_URL`/`DATABASE_URL`.
*Frontend workaround:* none that is correct. Optionally: after ~60 s in `queued`, show "sync worker unavailable".
*Fix before integration?* **Yes — this is the single most important item.**

---

**L3 — Analytics cache is invalidated *before* the transaction commits → up to 15 min of stale analytics. Severity: HIGH**
`app/services/sync_service.py:88-95` (upsert → `invalidate_repository_cache`) and `app/workers/tasks/sync_task.py:40-41` (`mark_completed` → `commit`). Same pattern in `app/services/webhook_service.py:80-86` (invalidate inside the handler; `get_db` commits after the response).
*Why it's a problem:* the invalidation is not atomic with the write. A concurrent analytics GET in that window reads **pre-write** data and re-caches it for 900 s.
*Example:* 12 s into a sync, a user opens the dashboard → overview is computed from old rows → written to Redis → after the sync finishes the dashboard still shows old numbers for 15 minutes, and reports `cached: true`.
*Frontend impact:* "the charts didn't update after syncing" — undebuggable from the client.
*Backend fix:* invalidate **after** the commit (`await db.commit()` then invalidate), or invalidate twice (before and after), or use a short "generation" key.
*Frontend workaround:* none reliable (no cache-bypass param). Mitigation: keep refetching for a couple of minutes after a sync completes and hope the TTL-locked entry expires. Unacceptable for a dashboard.
*Fix before integration?* **Yes.**

---

**L4 — GitHub rate limits and API errors surface as 500, and secondary limits are not detected at all. Severity: HIGH**
`app/integrations/github/client.py:154-166` raises `GitHubRateLimitError` **only** when `status == 403 and "rate limit" in response.text.lower()`. `app/api/v1/workspaces.py:99-103` (connect) catches only `(GitHubAuthError, GitHubNotFoundError)`; `:176-195` (track) catches `(GitHubNotConnectedError, GitHubNotFoundError, GitHubRateLimitError, GitHubAuthError)`. `GitHubAPIError` and `GitHubAppConfigError` are never caught on either route.
*Why it's a problem:* GitHub's **secondary** rate limits return `403` with `"secondary rate limit"` or `429`; neither contains `"rate limit"` in the checked form for the 429 case, and both bypass the handler. Remaining `GitHubAPIError`s → unhandled → 500.
*Example:* a large org triggers a secondary limit → the user clicks "Track repository" → **500 Internal Server Error** instead of 429/503 with a reset time.
*Frontend impact:* cannot distinguish "try again in 20 s" from "the server is broken"; the 429 UI path is effectively dead code.
*Backend fix:* treat `403`/`429` + `Retry-After` as rate limiting; catch `GitHubAPIError`/`GitHubAppConfigError` on every GitHub route and map to 429/502/500 with a structured body.
*Frontend workaround:* treat 500 on track/connect as "possibly rate-limited" and offer retry. Poor UX.
*Fix before integration?* **Yes (client.py + route handlers).**

---

**L5 — Webhook signature verification is silently skipped when the secret is unset. Severity: HIGH (fail-open)**
`app/api/v1/webhooks.py:30-36`: `if webhook_secret:` — an empty/None `GITHUB_WEBHOOK_SECRET` means **any unauthenticated POST is accepted**, and its payload is upserted into `pull_requests`.
*Why it's a problem:* fail-open security control; a single missing env var turns the endpoint into an unauthenticated write primitive.
*Example:* an attacker (or a misconfigured deploy) POSTs a forged `pull_request` payload for a tracked repo → arbitrary PR rows, arbitrary analytics.
*Frontend impact:* corrupted charts with no indication of why.
*Backend fix:* refuse the request (503/500) when the secret is unconfigured, instead of skipping verification.
*Frontend workaround:* none.
*Fix before integration?* **Yes** (cheap).

---

**L6 — `installation_id` is globally unique, so connecting a shared installation returns 500. Severity: MEDIUM**
`app/models/workspace.py:23-25` (`unique=True`), migration `b8c3d1e2f4a5`. `github_service.connect_installation` performs a SELECT-less write; the `IntegrityError` is raised at commit (after the response is built) and is unhandled.
*Why it's a problem:* GitHub installations are per-account, not per-tenant. Two workspaces (even owned by different users) legitimately want the same installation.
*Example:* Alice connects org `acme` to workspace A. Bob (also an org admin) connects the same installation to workspace B → **500**.
*Frontend impact:* an unexplained 500 in the connect flow.
*Backend fix:* decide the model deliberately — either drop the uniqueness and allow N workspaces per installation (best, and matches `list_by_github_id`'s multi-workspace semantics), or return a clear 409.
*Frontend workaround:* none.
*Fix before integration?* **Yes — a decision is needed.**

---

**L7 — Concurrent `track` calls can 500. Severity: LOW**
`app/repositories/repository_repository.py:51-90` — SELECT-then-INSERT on `(workspace_id, github_id)`.
*Why:* two simultaneous requests race between the SELECT and the INSERT → `IntegrityError` → 500.
*Example:* a double-clicked "Track" button.
*Frontend impact:* a spurious error toast; a retry then succeeds.
*Backend fix:* use `ON CONFLICT DO UPDATE` (as `upsert_batch` already does).
*Frontend workaround:* disable the button while the mutation is in flight (do this anyway).
*Fix before integration?* No — but the button guard is mandatory.

---

**L8 — A misconfigured Supabase setup returns 500 instead of 401. Severity: MEDIUM**
`app/integrations/auth/verifier.py:52-53` raises `TokenVerificationError`; `app/api/dependencies.py:50` catches **only** `InvalidTokenError`.
*Why:* the two error classes are meant to be distinguished (`exceptions.py` defines both) but the dependency collapses only one.
*Example:* a deploy forgets `SUPABASE_JWKS_URL` → every authenticated request returns 500.
*Frontend impact:* the auth-error UI never triggers; the app appears totally broken.
*Backend fix:* catch `TokenVerificationError` → 401/503.
*Frontend workaround:* treat 500 on authenticated routes as a possible auth misconfiguration.
*Fix before integration?* **Yes** (small).

---

**L9 — Analytics `days` can never be `None`, contradicting the documented all-time mode. Severity: MEDIUM**
`app/api/v1/analytics.py:34-39` and `:158-163`. Empirically: omitted → 30; `?days=` → 422; `?days=null` → 422.
*Why:* the parameter is documented (in `Query(description=…)` **and** `docs/api.md`) as nullable-for-all-time, but the declared default makes `None` unreachable over HTTP.
*Example:* a frontend "All time" toggle sends `days=null` → 422 → the toggle is broken.
*Frontend impact:* "All time" range selection is impossible; the UI must not offer it.
*Backend fix:* either `days: int | None = Query(None, …)` (changes the default to all-time) or add an explicit `all_time: bool = False`, then fix the descriptions/docs.
*Frontend workaround:* never send `days` for all-time; cap the picker to 365 days and document that the data is creation-windowed.
*Fix before integration?* **Yes — at least a documentation fix, so nobody builds an "All time" control.**

---

**L10 — No sync-job deduplication → concurrent full syncs. Severity: MEDIUM**
`app/api/v1/workspaces.py:291-303`. Every POST inserts a new `queued` job unconditionally. `sync_jobs` has no partial unique index on active states.
*Why:* N clicks ⇒ N full GitHub paginations and N concurrent `ON CONFLICT` writers on the same rows (lock waits; possible deadlocks), plus N cache invalidations.
*Example:* a user clicks "Sync" three times → 3 × up to 5000 PRs fetched → rate limiting.
*Frontend impact:* wasted minutes, higher 429/500 rates, confusing job history.
*Backend fix:* reject with 409 when a `queued`/`processing` job already exists for the repository (partial unique index).
*Frontend workaround:* poll `GET .../sync-jobs?limit=1` before enabling the button.
*Fix before integration?* Recommended; the frontend guard alone is an acceptable stopgap.

---

**L11 — Silent truncation at 5000 PRs. Severity: MEDIUM**
`app/integrations/github/client.py:235-266`: `max_pages: int = 50`, `per_page = 100`, loop ends when `page > 50` **or** a short page is returned. No signal is returned to the caller.
*Why:* a repository with >5000 PRs is partially mirrored, yet the job reports `completed` with `total_synced: 5000` and no warning.
*Example:* a 9000-PR monorepo → the week chart silently omits the oldest PRs and `total_prs` is under-reported.
*Frontend impact:* charts are wrong with no error state; the user has no way to know.
*Backend fix:* surface `truncated: true` / a `SyncJobResponse` warning field, or paginate by `merged_at`/`updated` date ranges.
*Frontend workaround:* show a warning when `total_synced == 5000`.
*Fix before integration?* Medium priority — the frontend guard is cheap.

---

**L12 — The authors endpoint is capped at 20 rows with no indication. Severity: MEDIUM**
`app/repositories/analytics_repository.py:335` `limit: int = 20`; not exposed by `app/api/v1/analytics.py:151-178`; `AuthorMetricsResponse` has no `total`/`truncated`.
*Example:* a repo with 35 contributors shows 20; the UI implies a complete list.
*Frontend impact:* misleading contributor leaderboard; a "show all" control cannot be built.
*Backend fix:* expose `limit` and/or return `total_authors`.
*Frontend workaround:* label the list "Top 20 contributors".
*Fix before integration?* Defer — the label is an honest workaround.

---

**L13 — `state` filter is unvalidated and silently returns an empty list. Severity: LOW-MEDIUM**
`app/api/v1/workspaces.py:378` (`state: str | None`), `app/repositories/pull_request_repository.py:49,64`.
*Example:* `?state=merged` → 200 `{"items":[],"total":0}` — the UI shows "no pull requests" for a repo with 200 PRs.
*Frontend impact:* a wrong-looking empty state.
*Backend fix:* `Literal["open","closed","all"]` → 422 on anything else.
*Frontend workaround:* only ever send `open`/`closed`, or omit the param. Derive "merged" client-side from `merged_at != null` (filtering locally is a display concern, not analytics).
*Fix before integration?* Low — trivially guarded frontend-side.

---

**L14 — Missing composite indexes for the analytics and PR-list queries. Severity: MEDIUM (performance)**
Migration `7b756be28dfc` creates `ix_pull_requests_repository_id`, `ix_pull_requests_github_id`, `ix_pull_requests_node_id` — **no index on `merged_at` or `github_created_at`**. Every analytics query filters `repository_id = ? AND merged_at >= ?` (or `github_created_at >= ?`); `list_by_repository` also sorts by `number DESC` with no `(repository_id, number)` index.
*Example:* a tracked repo with 500k PRs → each of the 5 endpoints does a bitmap scan + sort over the whole repository partition, over HTTP, on every cache miss.
*Frontend impact:* slow first paint after a cache miss/invalidation; charts appear to hang.
*Backend fix:* add `(repository_id, merged_at)`, `(repository_id, github_created_at)`.
*Frontend workaround:* keep queries cached; rely on `staleTime`.
*Fix before integration?* Recommended if any real repository is tracked; otherwise deferrable.

---

**L15 — The activity endpoint omits the partial-bucket flag. Severity: LOW-MEDIUM**
`app/repositories/analytics_repository.py:57-70` (`fill_day_counts`) has no `is_partial`, unlike `fill_week_counts`/`fill_week_percentiles`.
*Why:* the last day is always today, so both counts are always incomplete, with no field to say so.
*Example:* `created_count` reads 3 at 09:00 and 11 by end of day; `days_analyzed` doesn't reveal the bucket is partial.
*Frontend impact:* the trend line always dips at the right edge; users read it as a slowdown.
*Backend fix:* add `is_partial: bool` to `ActivityTrendItem` (last item only). **Changing a response schema is a breaking change** — decide before the frontend binds to the type.
*Frontend workaround:* treat `data[data.length−1].day` as today (UTC) and de-emphasise/drop it.
*Fix before integration?* **Yes — because it's a schema change and it's cheap now.**

---

**L16 — `week_start`/`day` are timezone-less ISO strings. Severity: HIGH (frontend correctness)**
`app/repositories/analytics_repository.py:49,65,84` call `.isoformat()` on **naive** datetimes → `"2026-09-14T00:00:00"` (no `Z`, no offset). Asserted by `test_analytics.py:402,410,419`.
*Why:* JavaScript parses a date-time **without** an offset as **local time** (`ECMAScript` `Date.parse` for date-time forms). Every bucket label is therefore shifted by the browser's UTC offset.
*Example:* a UTC+5:30 user sees the week starting `2026-09-14 05:30` local — the "Monday" axis label reads correctly but `is_partial`-adjacent logic and tooltips (`new Date(week_start).toLocaleDateString()`) can render the **previous day** in negative-offset zones (UTC−5 → `2026-09-13`).
*Frontend impact:* mislabelled axes and tooltips; possible off-by-one day/week.
*Backend fix:* emit `datetime.isoformat() + "Z"` (or attach `tzinfo=UTC` before serialising) so the contract is unambiguous. **This is a breaking change to the wire format — do it now, before integration.**
*Frontend workaround:* always normalise with `` new Date(`${week_start}Z`) ``; never pass the raw string to `new Date()`. Also note `timestamptz` fields (`created_at`, `merged_at`, …) **are** returned with an offset, so the two families of timestamps are inconsistent.
*Fix before integration?* **Yes.**

---

**L17 — Analytics window bases are inconsistent across endpoints. Severity: MEDIUM**
`overview`/`authors` filter by **`github_created_at`** (`analytics_repository.py:129,356`); `throughput`/`cycle-time-trend` filter by **`merged_at`**; `activity` uses both for two different series.
*Example:* `days=30` on Overview and `weeks=4` on Cycle-Time-Trend cover **different sets of PRs**. A PR created 45 days ago and merged yesterday appears in Cycle-Time-Trend but not in Overview's `merged_prs`.
*Frontend impact:* the dashboard's own numbers look self-contradictory (e.g. "Merged 40" on the card vs a 60-PR bar total in the chart) — an obvious user-visible inconsistency.
*Backend fix:* document it precisely and/or add a `window_basis` field, or make Overview merge-date-based.
*Frontend workaround:* label the Overview window as "PRs opened in the last 30 days", not "the last 30 days".
*Fix before integration?* **Yes — at minimum, precise labels.**

---

**L18 — Fire-and-forget in-process task with no reference. Severity: LOW**
`app/workers/queue.py:55-61`: `asyncio.create_task(run_sync_job(...))` result is discarded.
*Why:* Python documents that a task can be garbage-collected mid-execution if nothing references it; it can also be cancelled on shutdown.
*Example:* Redis blips during the POST → the job runs in the API process and is destroyed mid-flight → the job is stuck in `processing` (worse than `queued`, because `started_at` is set) with no reaper.
*Frontend impact:* an indefinite `processing` state; the frontend must time out.
*Backend fix:* keep a module-level set of tasks; add a stale-job reaper.
*Frontend workaround:* time-box polling and show a stuck state.
*Fix before integration?* No (guard frontend-side), but the reaper matters operationally.

---

**L19 — No GitHub installation-lifecycle webhooks. Severity: MEDIUM**
`app/services/webhook_service.py:51-52` ignores `installation` / `installation_repositories`.
*Example:* the org admin uninstalls the App on GitHub → `workspaces.github_installation_id` stays set, `is_github_connected` stays `true`, `GET /github/repositories` starts returning 400/502, and every sync fails.
*Frontend impact:* a "Connected ✓" badge lies; there is no event to trigger the disconnect.
*Backend fix:* handle `installation` (`deleted`) → null out matching workspaces; handle `installation_repositories`.
*Frontend workaround:* on a 400/502 from the repo-listing or sync flow, surface "GitHub connection may have been revoked — reconnect".
*Fix before integration?* Recommended; the frontend workaround is acceptable v1.

---

**L20 — `state` in the install URL is never verified. Severity: LOW-MEDIUM**
`github_service.py:31-40` embeds the raw `workspace.id`; the connect endpoint accepts any `installation_id` without checking `state`, and there is no nonce or expiry.
*Why:* classic login-CSRF shape — an attacker-supplied `install_url` (with the attacker's own installation via a crafted flow) could be fed to a victim owner; the frontend must not blindly trust a URL-provided `installation_id`.
*Frontend impact:* if the frontend forwards `installation_id` from the redirect without confirming the user just completed the flow, it can bind the wrong installation.
*Backend fix:* signed, single-use `state` (HMAC + TTL).
*Frontend workaround:* only call `connect` from the callback page immediately after a user-initiated install, and verify the persisted `state` equals the workspace currently selected.
*Fix before integration?* No — document and guard frontend-side; ship the signed-state improvement later.

---

**L21 — Non-issues I explicitly verified (to be precise, not vague)**
- ✅ **Zero filling:** verified present for weeks and days.
- ✅ **Percentile math:** `percentile_cont` is the correct continuous/interpolated percentile; NULLs are excluded; results are rounded once, at the edge.
- ✅ **Off-by-one in bucket construction:** `monday − (weeks−1−i)` produces exactly `weeks` buckets ending on this Monday. Correct.
- ✅ **Upsert idempotency / webhook replay:** `ON CONFLICT (repository_id, number) DO UPDATE` — replays are safe and non-duplicating.
- ✅ **Duplicate PRs:** prevented by `uq_pull_requests_repo_number` — no duplicates possible.
- ✅ **Cross-tenant read leaks:** none found. Every analytics/PR/sync-jobs endpoint runs a `repo.workspace_id == workspace.id` check before touching data, and **before** the cache read, so cache keys cannot leak across tenants.
- ✅ **Authorization bypass:** none found; owner-only endpoints all use `get_owned_workspace`.
- ✅ **N+1 queries:** none in the request path; each handler issues 1–3 statements.
- ✅ **Empty repository:** all five endpoints return well-formed empty/zero/`null` payloads (details in Phase 12).
- ✅ **Stale Redis after untrack:** the repository row is deleted (cascade), so its cache keys become unreachable garbage that expires within 900 s — harmless.
- ✅ **Reopened PRs:** GitHub sends `state: "open"`, `merged_at: null` → the upsert resets `merged_at`/`closed_at` to `NULL`. Correct.
- ✅ **Closed-unmerged PRs:** counted by `state='closed' AND merged_at IS NULL`. Correct; kept out of `merged_prs`.
- ✅ **`cached` flag correctness:** forced to `true` on hits and `false` on misses; the flag itself is reliable (the *freshness* of a hit is not — see L3).
- ✅ **Unit tests:** 79 pass. **⚠️ But the entire SQL layer is untested** — every analytics test mocks `AnalyticsRepository`, and `upsert_batch`/`percentile_cont`/`date_trunc` are never executed against PostgreSQL. The `IntegrationError`-class risks above are exactly the ones unit tests cannot catch.

---

# PHASE 9 — FRONTEND DATA MAPPING

Rules applied: the frontend may only format dates, format numbers, convert units, choose presentation, and handle loading/error/empty. **No merge-rate, no cycle-time, no percentile, no gap-filling computation client-side.**

| # | Component | Endpoint | Query | Fields used | Transform | Loading | Empty | Error | Cache/stale | Refresh |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Overview KPI cards** | `…/analytics/overview` | `days=30` | `total_prs`, `open_prs`, `merged_prs`, `closed_unmerged_prs`, `merge_rate_percentage`, `cycle_time.{p50,p90,avg}_hours`, `cached` | Hours → human ("3.2 h" / "1.5 d") — **unit conversion only**. `null` → `—`, **never 0**. Percentage: print `merge_rate_percentage.toFixed(1) + "%"`, `null` → `—` | Skeleton cards | All zeros + nulls → "No PRs yet — run a sync" | 401 → sign in; 403 → no access; 404 → pick another repo; 500 → retry | Show a subtle "cached" badge when `cached === true` | On mount, on `repositoryId` change, after a sync job completes, on window focus |
| 2 | **Throughput chart (bars)** | `…/analytics/throughput` | `weeks=8` | `data[].week_start`, `data[].merged_count`, `data[].is_partial`, `weeks_analyzed`, `cached` | X label: `` new Date(`${week_start}Z`) `` → `MMM d` (**append Z!**). Style `is_partial` bars differently (hatched/lighter). Pass `data` **as-is** — do not fill gaps | Chart skeleton | All `merged_count === 0` → empty-state overlay | Banner + retry | Same | On mount, repo change, post-sync, focus |
| 3 | **Activity chart (dual line)** | `…/analytics/activity` | `days=30` | `data[].day`, `data[].created_count`, `data[].merged_count`, `days_analyzed` | `` new Date(`${day}Z`) ``. Two series from one array. ⚠️ **No `is_partial`** — compute `isToday = day === todayUtcIso` **for styling only** (this is not backend logic) | Chart skeleton | All zeros | Banner + retry | Same | Same |
| 4 | **Cycle-time trend (line, 3 series)** | `…/analytics/cycle-time-trend` | `weeks=12` | `data[].week_start`, `.p50_hours`, `.p90_hours`, `.avg_hours`, `.is_partial` | `` new Date(`${week_start}Z`) ``. **`null` must break the line** (`spanGaps: false` / `connectNulls: false`) — never interpolate to 0. Hours → days optionally | Chart skeleton | All three series all-null → "No merges in the last 12 weeks" | Banner + retry | Same | Same |
| 5 | **Contributor leaderboard** | `…/analytics/authors` | `days=30` | `authors[].author_login`, `.total_prs`, `.merged_prs`, `.avg_cycle_time_hours` | Bar/width = `total_prs / max(total_prs)` — **presentation normalisation, not analytics**. `avg_cycle_time_hours` null → `—`. **Label "Top 20 contributors"** (L12) | Row skeletons | `authors: []` → "No contributors with PRs in this window" | Banner + retry | Same | Same |
| 6 | **Workspace switcher** | `GET /workspaces` | — | `id`, `name`, `created_at` | Sort/format | Dropdown skeleton | `[]` → create-workspace prompt | Retry | `staleTime` 5 min | After create |
| 7 | **GitHub connection card** | `GET /workspaces/{id}` | — | `is_github_connected`, `github_installation_id` | — | Skeleton | `false` → "Connect GitHub" CTA | Retry | `staleTime` 30 s, refetch on focus | After connect/disconnect |
| 8 | **Install button** | `GET …/github/install-url` | — | `install_url` | `window.location.assign(url)` or popup | Button spinner | — | 403 → hide (member) + tooltip; 500 → "GitHub App not configured on this server" | Fetch on click, `staleTime` 0 | On demand |
| 9 | **Install-callback page** | `POST …/github/connect` | body `{installation_id}` | `is_github_connected` | Read `installation_id`+`state` from `window.location.search`; compare `state` to the stored `workspace_id` | Full-page spinner | — | 400 → "We couldn't verify that installation"; 500 → "Try again" (possibly rate-limited/duplicate — L6/L7) | — | Invalidate the workspace query on success |
| 10 | **Repo picker ("available")** | `GET …/github/repositories` | `page=1&per_page=100` | `github_id`, `full_name`, `private`, `description`, `default_branch` | Group by `full_name.split("/")[0]`; badge for `private` | List skeleton | 400 → "Connect GitHub first" (not "no repos") | 429 → "GitHub rate limit — retry at X"; 502 → "GitHub auth error"; 500 → generic | `staleTime` 60 s | On open; refetch on 429 after `Retry-After`/reset |
| 11 | **"Tracked" badge** | `GET …/repositories/tracked` | — | `id`, `full_name`, `is_tracked` | **Join to #10 on `full_name`** (L: `RepositorySummary` has no `github_id`) | — | `[]` → "No repositories tracked" | Retry | `staleTime` 30 s | After track/untrack |
| 12 | **Track button** | `POST …/repositories/track` | body `{owner, repo}` | `id`, `full_name` | Split `full_name` into `owner`/`name` | Button spinner, **disable** while pending (L7) | — | 400 → "Connect GitHub first"; 404 → "Repository not found or not visible to the installation"; 429 → rate-limit UI; 500 → retry | — | Invalidate #10, #11, and all 5 analytics keys |
| 13 | **Repo detail header** | `GET …/repositories/tracked/{id}` | — | `full_name`, `owner_login`, `html_url`, `default_branch`, `private`, `description`, `github_id` | — | Skeleton | — | 404 → "Repository no longer tracked" → redirect | `staleTime` 60 s | On mount |
| 14 | **Sync button** | `POST …/tracked/{id}/sync` | — | `job_id`, `status`, `message` | Store `job_id` | Button spinner → "Syncing…" | — | 400 → "Workspace not connected to GitHub"; 404 → repo gone; 403 → member (hide) | — | Start polling; on completion invalidate all 5 analytics keys |
| 15 | **Sync progress** | `GET …/sync-jobs/{job_id}` | — | `status`, `created_at`, `started_at` | Elapsed = `now − created_at`; progress is **indeterminate** (no % field) | Progress bar (indeterminate) | — | 404 → **job vanished (repo untracked)** → stop, show error | `staleTime` 0, `refetchInterval` while non-terminal | 2 s → 5 s after 15 s; hard-stop at 120 s → "worker unavailable" (L2) |
| 16 | **Sync history** | `GET …/sync-jobs` | `limit=10` | full `SyncJobResponse[]` | Format `total_synced` as **"PRs processed"** (L: not "new"); status pill; show `error_message` verbatim | Table skeleton | `[]` → "No syncs yet" | Retry | `staleTime` 10 s | After a sync completes |
| 17 | **PR table** | `GET …/pull-requests` | `state`, `page`, `per_page=50` | all `PullRequestResponse` fields + `total`/`page`/`per_page` | `state` → badge; **merged ⇔ `merged_at !== null`** (derive, don't send `state=merged` — L13); `null` author → "ghost"; `total` → "Showing X–Y of N" using `page`/`per_page` | Table skeleton | `total === 0` → "No PRs synced yet — run a sync" | **404 mid-poll if untracked**; 422 if `per_page > 100` | `staleTime` 30 s, `keepPreviousData` for paging | Page change; focus; after sync |
| 18 | **"Analytics not ready" state** | derived | — | overview `total_prs === 0` + `sync-jobs` `[]`/all failed | — | — | Show "Run your first sync" | — | — | — |

**Explicitly forbidden client-side work (and what the backend already gives you instead)**
| Don't compute | Because the backend already returns |
|---|---|
| merge rate | `merge_rate_percentage` (already `merged/(merged+closed_unmerged)*100`) |
| cycle time | `cycle_time.p50/p90/avg_hours` and `authors[].avg_cycle_time_hours` |
| percentiles | `percentile_cont` in SQL (`analytics_repository.py:122-124,296-298`) |
| fill missing weeks/days | `fill_week_counts` / `fill_day_counts` — arrays are already dense and exactly `weeks`/`days` long |
| partial-week flag | `is_partial` (weeks only; for activity it's a display-only heuristic, L15) |
| PR totals | `total_prs` / `PullRequestListResponse.total` |
| "is merged" from `state` | `state` is only `open`/`closed`; use `merged_at` |
| total author count | **not available** → label "Top 20" instead of computing |

---

# PHASE 10 — TANSTACK QUERY / DATA FETCHING PLAN

```ts
// ---------- Query keys (all keyed by workspace scope) ----------
["me"]                                                              // GET /me
["workspaces"]                                                      // GET /workspaces
["workspace", workspaceId]                                          // GET /workspaces/{id}
["workspace", workspaceId, "githubRepositories", { page, perPage }]  // GET .../github/repositories
["workspace", workspaceId, "repositories"]                          // GET .../repositories/tracked
["repository", repositoryId]                                        // GET .../tracked/{id}
["repository", repositoryId, "syncJobs", { limit }]                 // GET .../sync-jobs
["repository", repositoryId, "syncJob", jobId]                      // GET .../sync-jobs/{jobId}
["repository", repositoryId, "pullRequests", { state, page, perPage }]
["repository", repositoryId, "analytics", "overview",     { days }]  // ← days is in the key
["repository", repositoryId, "analytics", "throughput",   { weeks }]
["repository", repositoryId, "analytics", "activity",     { days }]
["repository", repositoryId, "analytics", "cycleTime",    { weeks }]
["repository", repositoryId, "analytics", "authors",      { days }]
```

`repositoryId` alone is sufficient — it is globally unique (UUID) and server-side access is re-checked against `workspaceId`. Keeping `workspaceId` in the key is still worthwhile so that switching workspaces doesn't reuse another tenant's data while `workspaceId` is in flux. **That is a UI-lifecycle convenience, not a security boundary** (the backend enforces access on every request).

| Query | Runs when | Refetch triggers | `staleTime` | Polling | Invalidation |
|---|---|---|---|---|---|
| `["me"]` | after session established | — | 5 min | no | on sign-in |
| `["workspaces"]` | app shell mounts | focus | 5 min | no | after `POST /workspaces` |
| `["workspace", id]` | workspace selected | focus | **30 s** (drives the connection badge) | no | after connect/disconnect |
| `githubRepositories` | GitHub-connect UI opens | focus, manual | 60 s | no | after connect + after track |
| `repositories` | workspace selected | focus | 30 s | no | after track/untrack |
| `["repository", id]` | repo selected | focus | 60 s | no | after untrack (→ 404, so remove the query) |
| `syncJob` | `job_id` available **and** status non-terminal | `refetchInterval` | **0** | **2 s → 5 s after 15 s; abort at 120 s** | on terminal state |
| `syncJobs` | sync panel visible | completion of `syncJob` | 10 s | no (or 15 s while a sync runs) | after `POST /sync` |
| `pullRequests` | PR tab visible | page change, focus | 30 s | no | after sync completion |
| **all 5 analytics** | repo + tab visible | focus | **60 s** | optional 120 s while a dashboard is open | **after a sync job reaches `completed`**, and after track/untrack |

**Dependent queries:** `syncJob` must be `enabled: !!jobId && !isTerminal`; `analytic*` must be `enabled: !!repositoryId`. Analytics queries should **not** be chained behind the sync job — render with the cached/stale data and invalidate on completion (the backend invalidates its own cache anyway).

**`staleTime` rationale:** the backend serves a 15-minute Redis cache, so a short `staleTime` (30–60 s) is a UX trade, not a correctness one. Since the backend **cannot** be forced to bypass its cache and its invalidation races the commit (L3), the frontend's own refetching is the only freshness lever it has. Keep `staleTime` low and rely on `refetchOnWindowFocus`.

**Do NOT** use `retry: 3` blanket-style: only retry idempotent GETs, and **never** auto-retry `POST /sync` or `POST /track` (L7, L10). Use `retry: false` for those mutations.

**Optimistic updates:** none. Every mutation depends on server-side GitHub verification.

---

# PHASE 11 — TYPESCRIPT TYPES

Derived strictly from `app/schemas/*.py`. Nullable fields are exactly as declared.

```ts
/* ------------------------------------------------------------------ */
/* Auth / user                                                         */
/* ------------------------------------------------------------------ */
/** app/schemas/user.py::UserResponse */
export interface UserResponse {
  id: string;                // uuid
  email: string | null;
  name: string | null;
  avatar_url: string | null;
  created_at: string;        // ISO 8601 with offset (timestamptz)
  updated_at: string;
}

/* ------------------------------------------------------------------ */
/* Workspace                                                           */
/* ------------------------------------------------------------------ */
export interface WorkspaceCreateRequest { name: string; }   // min 1, max 255

/** app/schemas/workspace.py::WorkspaceSummary */
export interface WorkspaceSummary {
  id: string;
  name: string;
  github_installation_id: number | null;   // bigint; safe as number in practice
  created_at: string;
  // NOTE: no is_github_connected here — derive from github_installation_id !== null
}

/** app/schemas/workspace.py::WorkspaceResponse */
export interface WorkspaceResponse {
  id: string;
  name: string;
  github_installation_id: number | null;
  created_at: string;
  updated_at: string;
  is_github_connected: boolean;            // computed field
  // NOTE: no `role` field exists — see L1
}

/* ------------------------------------------------------------------ */
/* GitHub                                                              */
/* ------------------------------------------------------------------ */
/** app/schemas/github.py */
export interface GitHubInstallUrlResponse { install_url: string; }
export interface GitHubConnectRequest { installation_id: number; }  // > 0

export interface GitHubRepositoryResponse {
  github_id: number;
  node_id: string;
  name: string;
  full_name: string;
  private: boolean;
  html_url: string;
  default_branch: string;
  description: string | null;
}

/* ------------------------------------------------------------------ */
/* Repository                                                          */
/* ------------------------------------------------------------------ */
export interface RepositoryTrackRequest { owner: string; repo: string; }  // each 1..255

/** app/schemas/repository.py::RepositorySummary */
export interface RepositorySummary {
  id: string;
  name: string;
  full_name: string;
  private: boolean;
  is_tracked: boolean;
  html_url: string;
  default_branch: string;
  // NOTE: no github_id / workspace_id / owner_login / timestamps
}

/** app/schemas/repository.py::RepositoryResponse */
export interface RepositoryResponse {
  id: string;
  workspace_id: string;
  github_id: number;
  node_id: string;
  name: string;
  full_name: string;
  owner_login: string;
  private: boolean;
  html_url: string;
  default_branch: string;
  description: string | null;
  is_tracked: boolean;
  created_at: string;
  updated_at: string;
}

/* ------------------------------------------------------------------ */
/* Sync jobs                                                           */
/* ------------------------------------------------------------------ */
/** Runtime values from sync_job_repository; the schema declares `status: string`. */
export type SyncJobStatus = "queued" | "processing" | "completed" | "failed";

/** app/schemas/sync_job.py::SyncJobCreateResponse */
export interface SyncJobCreateResponse {
  job_id: string;
  status: string;      // observed: "queued"
  message: string;     // observed: "Synchronization task enqueued successfully"
}

/** app/schemas/sync_job.py::SyncJobResponse */
export interface SyncJobResponse {
  id: string;
  workspace_id: string;
  repository_id: string;
  status: SyncJobStatus | string;   // narrowed union + escape hatch
  total_synced: number;             // PRs FETCHED & upserted this run (capped at 5000)
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

/* ------------------------------------------------------------------ */
/* Pull requests                                                       */
/* ------------------------------------------------------------------ */
/** app/schemas/pull_request.py::PullRequestResponse */
export interface PullRequestResponse {
  id: string;
  repository_id: string;
  github_id: number;
  node_id: string;
  number: number;
  title: string;
  state: "open" | "closed";    // GitHub never emits "merged"
  draft: boolean;
  author_login: string | null;
  html_url: string;
  merged_at: string | null;    // merged ⇔ merged_at !== null
  closed_at: string | null;
  github_created_at: string;
  github_updated_at: string;
  created_at: string;
  updated_at: string;
}

export interface PullRequestListResponse {
  items: PullRequestResponse[];
  total: number;
  page: number;
  per_page: number;
}

/* ------------------------------------------------------------------ */
/* Analytics                                                           */
/* ------------------------------------------------------------------ */
export interface CycleTimeMetrics {
  p50_hours: number | null;
  p90_hours: number | null;
  avg_hours: number | null;
}

/** app/schemas/analytics.py::RepositoryMetricsResponse */
export interface RepositoryMetricsResponse {
  repository_id: string;
  time_window_days: number | null;   // always 30 in practice (L9)
  total_prs: number;
  open_prs: number;
  merged_prs: number;
  closed_unmerged_prs: number;
  merge_rate_percentage: number | null;
  cycle_time: CycleTimeMetrics;
  cached: boolean;
}

export interface WeeklyThroughputItem {
  week_start: string;      // ⚠️ naive UTC ISO — append "Z" before Date()
  merged_count: number;
  is_partial: boolean;     // true on the last item only
}
export interface WeeklyThroughputResponse {
  repository_id: string;
  weeks_analyzed: number;
  data: WeeklyThroughputItem[];   // exactly `weeks_analyzed` items
  cached: boolean;
}

export interface ActivityTrendItem {
  day: string;             // ⚠️ naive UTC ISO — append "Z"
  created_count: number;
  merged_count: number;
  // NOTE: no is_partial (L15)
}
export interface ActivityTrendResponse {
  repository_id: string;
  days_analyzed: number;
  data: ActivityTrendItem[];      // exactly `days_analyzed` items
  cached: boolean;
}

export interface CycleTimeTrendItem {
  week_start: string;      // ⚠️ naive UTC ISO — append "Z"
  p50_hours: number | null;
  p90_hours: number | null;
  avg_hours: number | null;
  is_partial: boolean;     // true on the last item only
}
export interface CycleTimeTrendResponse {
  repository_id: string;
  weeks_analyzed: number;
  data: CycleTimeTrendItem[];     // exactly `weeks_analyzed` items
  cached: boolean;
}

export interface AuthorMetricsItem {
  author_login: string;                 // non-null here; NULL authors are excluded server-side
  total_prs: number;
  merged_prs: number;
  avg_cycle_time_hours: number | null;
}
export interface AuthorMetricsResponse {
  repository_id: string;
  time_window_days: number | null;
  authors: AuthorMetricsItem[];         // max 20 rows (L12)
  cached: boolean;
}

/* ------------------------------------------------------------------ */
/* Errors                                                              */
/* ------------------------------------------------------------------ */
/** HTTPException → detail is a plain string. */
export interface ApiErrorResponse { detail: string; }

/** FastAPI/Pydantic validation failure → detail is an array (status 422). */
export interface ApiValidationErrorItem {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}
export interface ApiValidationErrorResponse { detail: ApiValidationErrorItem[]; }

export type ApiError = ApiErrorResponse | ApiValidationErrorResponse;

/** Narrowing helper — 422 only. */
export const isValidationError = (e: ApiError): e is ApiValidationErrorResponse =>
  Array.isArray((e as ApiValidationErrorResponse).detail);

/* Endpoint-specific query params */
export interface AnalyticsWindowDays { days?: number; }    // 1..365, default 30
export interface AnalyticsWindowWeeks { weeks?: number; }  // 1..52, default 8 or 12
export interface PullRequestQuery { state?: "open" | "closed" | "all"; page?: number; per_page?: number; }
```

---

# PHASE 12 — FRONTEND STATE MACHINE

Every transition below is justified by a **specific backend response**, not by assumption.

### Session
```
anonymous ──(Supabase session)──► authenticated
authenticated ──(401 "Invalid or expired token")──► refreshing ──(retry ok)──► authenticated
                                                └──(refresh fails)──► anonymous
authenticated ──(401 "Not authenticated" | "Invalid Authorization header")──► anonymous   (do NOT refresh)
authenticated ──(500 on an authed route)──► backend-misconfigured (L8)
```

### Workspace
```
loading ──► loaded            (200, ≥1 workspace)
        ──► empty             (200, [] → show "Create your first workspace")
        ──► error             (401 → sign in; 5xx → retry)
loaded ──► selected           (GET /workspaces/{id} 200)
        ──► forbidden        (403 "You do not have access to this workspace")
        ──► missing          (404 "Workspace not found" → drop from the list)
```

### Role / capability — **derived, because the API never states it (L1)**
```
unknown ──(200 on GET .../github/install-url)──► owner
        ──(403 "Owner permissions required for this action")──► member
```
Cache this per workspace for the session. All owner-only controls render **disabled + tooltip** — never rely on a click to discover the role.

### GitHub connection
```
unknown ──► not_connected   (WorkspaceResponse.is_github_connected === false)
        ──► connected       (is_github_connected === true)
not_connected ──(click Connect)──► install_pending   (persist {workspaceId} in sessionStorage, then redirect)
install_pending ──(callback has installation_id && state === workspaceId)──► connecting
     connecting ──(200)──► connected
                ──(400)──► install_failed      ("Unable to verify GitHub installation")
                ──(500)──► install_failed_generic  (rate limit OR already-linked — L6/L7)
                ──(missing state / mismatch)──► aborted (never call connect)
connected ──(revoked on GitHub's side; 400/502 from the repo picker or a failed sync)──► connection_stale
```
`connection_stale` is a **frontend-inferred** state (L19) — there is no backend signal.

### Repository
```
listing ──► available        (in GET .../github/repositories, not in GET .../repositories/tracked)
        ──► tracked          (matched on full_name)
tracking ──(POST /track 201)──► tracked
         ──(400 not connected)──► blocked_git_not_connected
         ──(404)──► not_found_on_github
         ──(429)──► rate_limited        (reset time when present)
         ──(500)──► tracking_error      (possibly rate limit / duplicate insert)
tracked ──► syncing ──(job queued)──► queued
                  ──(job processing)──► processing
                  ──(job completed)──► synced
                  ──(job failed)──► sync_failed (render error_message verbatim)
                  ──(no transition for >120 s)──► sync_stuck   (L2 — worker not deployed)
                  ──(404 while polling)──► untracked_midflight (repo deleted; stop polling)
synced ──► analytics available
untracked ──(DELETE 204)──► available   (drop the repo detail query; it will 404)
```

### Analytics (per endpoint, independently)
```
idle ──► loading
loading ──(200, cached=false, has data)──► fresh
        ──(200, cached=true,   has data)──► cached      → show a "cached" indicator; still schedule a refetch
        ──(200, all-zero/all-null)──► empty             → "No data for this window — run a sync"
        ──(401)──► unauthorized
        ──(403)──► forbidden
        ──(404)──► repository_missing                  → "Repository is no longer tracked"
        ──(422)──► invalid_query                       → clamp days 1..365 / weeks 1..52
        ──(5xx / network)──► error                     → retry affordance
fresh|cached ──(refetch in flight)──► refetching       → keep showing previous data (isFetching + isPlaceholderData)
refetching ──(sync job completed)──► loading (invalidate) ──► fresh
```

**Empty-state decision table (exact backend shapes)**
| Condition | Backend shape | UI |
|---|---|---|
| Repo tracked, never synced | overview: all counts `0`, `merge_rate_percentage: null`, all cycle-time `null`; throughput: `merged_count: 0` × weeks; activity: all zeros; cycle-time: all three `null` × weeks; authors: `[]` | "Run your first sync" — **not** "0% merge rate", **not** a flat 0-line chart |
| Synced, no merges ever | cycle-time-trend: every item `p50/p90/avg = null`; throughput: all `0` | Cycle-time chart shows **no line**; throughput shows all-zero bars |
| Synced, merges exist in some weeks only | cycle-time-trend: `null` on empty weeks | **Break the line** at nulls |
| Repo with no PRs at all | as row 1 | Same CTA |

---

# PHASE 13 — TESTING CONTRACT

## 13.1 Existing tests (79 unit tests, **all passing** — verified)

| File | Tests | Covers |
|---|---|---|
| `tests/unit/test_cors.py` | 4 | Preflight + simple requests from `localhost:5173` / `127.0.0.1:5173` allowed; unlisted origin not allowed |
| `tests/unit/test_health.py` | 2 | `/health` → `{"status":"ok"}` |
| `tests/unit/test_auth_dependency.py` | 4 | 401 for no header / wrong scheme / empty bearer / invalid token |
| `tests/unit/test_github_auth.py` | ~6 | App JWT (RS256, iat/exp), token caching, 403-rate-limit, non-201 |
| `tests/unit/test_github_client.py` | ~6 | Repo listing, single repo, PR parsing, pagination (100+1), header/token assertions |
| `tests/unit/test_github_webhooks.py` | 9 | HMAC valid/tampered/wrong-secret/malformed; ping; PR processed; PR untracked repo; **cache invalidation**; route ping; route 401 |
| `tests/unit/test_workspace_github_routes.py` | 5 | install-url (asserts `state` = workspace_id), connect (+`is_github_connected`), disconnect, repo list, not-connected 400 |
| `tests/unit/test_workspace_connect_serialization.py` | 2 | `MissingGreenlet` regression: connect must serialise after `refresh(["updated_at"])` |
| `tests/unit/test_repository_tracking.py` | 6 | track 201, not-connected 400, list, get, 404, untrack 204 |
| `tests/unit/test_pull_request_sync.py` | ~9 | Sync service success/tracked-errors, upsert call, PR list pagination, route 202 / 404, PR list route |
| `tests/unit/test_sync_jobs.py` | ~10 | Job repo create/transitions, queue redis + fallback, task success/failure, route polling + history + 404 |
| `tests/unit/test_analytics.py` | ~22 | Redis soft-fail; **cache hit**; **cache miss + set**; throughput; authors; activity; cycle-time trend; **all 5 routes**; **404**; `week_bucket_starts` Monday alignment; zero-fill + `is_partial`; null-preserving percentiles; **all 5 invalidation prefixes asserted in order** |
| `tests/integration/` | 12 | **Requires PostgreSQL.** Unauthenticated 401s; non-member 403; member 200; tenant isolation (2 users, 2 workspaces); workspace create/list/get; creator becomes owner; atomic create; user provisioning idempotency; duplicate identity → single user |

**Confirmed gaps (no test exists for any of these)**
- ❌ **No test executes a single line of analytics SQL.** Every `AnalyticsRepository` test mocks the repository. `percentile_cont`, `date_trunc`, `timezone('UTC', …)`, `ON CONFLICT` and the bucketing joins have **never run against PostgreSQL**.
- ❌ No test for `upsert_batch` SQL (`ON CONFLICT (repository_id, number)`).
- ❌ No test for `connect`/`track` receiving `GitHubRateLimitError` / `GitHubAPIError` (the 500 paths, L4).
- ❌ No test for the webhook route with an **unset** secret (L5).
- ❌ No test for `total_synced` semantics or the 5000-PR ceiling (L11).
- ❌ No integration test for any workspace-scoped route with a real DB (`/repositories/*`, `/analytics/*`, `/sync-jobs/*`).
- ❌ No test for `state` filter values, `per_page` bounds, or `days`/`weeks` boundaries at the HTTP layer.
- ❌ No test for `TokenVerificationError` → 500 (L8).

## 13.2 Tests that MUST pass before frontend integration

**Already existing — must stay green:** the entire `tests/unit` suite (79) **and** `tests/integration` (requires a Postgres test DB; `TEST_DATABASE_URL`, default `postgresql+psycopg://postgres:postgres@localhost:5432/github_intelligence_test`). CI (`.github/workflows/ci.yml`) additionally runs `ruff check .`, `ruff format --check .`, `mypy app tests`, `alembic upgrade head`, and coverage.

**Required new coverage — grouped by what the frontend depends on**

*Auth*
1. `/me` 401 with no header, non-bearer scheme, empty token, malformed token, expired token, wrong `iss`, wrong `aud`. *(currently only the first four)*
2. `TokenVerificationError` (Supabase unset) → **401 or 503, never 500** (L8).
3. Token refresh path: expired → 401 → new token → 200.

*Authorization*
4. Every owner-only route returns **403 `"Owner permissions required for this action"`** for a `member`:**all six**, one test each. *(none exist today)*
5. Every member route returns 200 for a `member`.
6. Non-member → 403; unknown workspace → 404; **the 403-vs-404 distinction is preserved** for every workspace route.
7. A workspace ID belonging to another user's tenant → 403 (not 404, not 200) on every resource route.
8. Cross-workspace repository ID (`repo belongs to workspace B`, accessed via workspace A) → **404** on all repository/analytics/sync routes.

*Workspace* — create (201 + owner row), list (ordering `created_at ASC`), get, 422 for empty/256-char name, `is_github_connected` computed correctly in both states.

*Repository* — track 201; re-track is idempotent and keeps the same `id`; track 404 for invisible repo; track 400 when disconnected; **two concurrent tracks → exactly one row, no 500** (L7); untrack 204 with an empty body; untrack cascades `pull_requests` and `sync_jobs`; list excludes untracked; **`RepositorySummary` contains no `github_id`** (contract lock).

*Sync*
9. POST `/sync` → 202 with `{job_id, status:"queued", message}`; the row is committed before `LPUSH`; `queued`→`processing`→`completed` with `started_at`/`completed_at` set; failure → `failed` + `error_message`; `rollback` runs before `mark_failed`.
10. `total_synced` equals the number of PRs submitted for upsert (not new rows) — a regression lock for the documented semantics.
11. Polling a job from another repository → 404; polling a job from another workspace → 404.
12. **A second concurrent sync for one repository** — assert current behaviour (multiple jobs) so the frontend guard is provably necessary (L10).
13. `limit` at 1, 50, 0, 51 → 200/200/422/422.

*Webhook*
14. `pull_request` with a tracked repo updates exactly that repo; multiple workspaces tracking the same `github_id` → all updated.
15. Untracked repo → `{"status":"ignored","reason":"repository_not_tracked"}` + 200 (GitHub must not see a failure).
16. `reopened` resets `merged_at`/`closed_at` to `NULL`.
17. `closed` without `merged_at` → `closed_unmerged_prs` increments and `merged_prs` does not.
18. Every non-`pull_request` event → `{"status":"ignored"}` + 200.
19. **Unset secret → request must be rejected, not processed** (L5).
20. Duplicate delivery of the same payload → exactly one PR row (idempotency).

*Analytics SQL (all new — against a real PostgreSQL)*
21. **Zero PRs** → overview all zeros + `merge_rate_percentage: null` + all cycle-time `null`; throughput `weeks`×`0`; activity `days`×`0/0`; cycle-time `weeks`×`null`; authors `[]`.
22. **One PR** (merged, 2 h) → `p50 === p90 === avg === 2.0`, `merge_rate_percentage === 100.0`, one author row.
23. **Multiple PRs** → assert exact percentile values against hand-computed expectations (the interpolated `percentile_cont` formula, not a naive rank) — this is the highest-value new test.
24. **Zero-merge weeks** → `p50/p90/avg` are **`null`, never `0`**, and `is_partial` is `false` for those weeks.
25. **Zero-activity days** → `{created_count: 0, merged_count: 0}` present, array length === `days`.
26. **Current partial week** → last item only has `is_partial: true`, and the bucket start is **this week's Monday** (and the series has exactly `weeks` items).
27. **Exact boundary merges** — `Mon 00:00:00.000 UTC`, `Sun 23:59:59.999 UTC`, `today 00:00:00 UTC` → assert bucket assignment for both throughput and activity.
28. **Timezone** — rows stored with `+05:30`/`-08:00` offsets bucket by UTC, not by local time.
29. **Window bases** — a PR created 40 days ago and merged yesterday appears in throughput/cycle-time-trend but **not** in overview `merged_prs` with `days=30` (L17) — a regression lock on the documented semantics.
30. **`state`/`merged_at` independence** — an open PR with `merged_at` set, and a closed PR without, are classified per the documented rules.
31. **Authors** — `author_login IS NULL` rows excluded; the **20-row cap** asserted; ordering by `total_prs DESC`; `avg_cycle_time_hours` `null` for a never-merged author.
32. **Invalid ranges** — `days=0`,`366`; `weeks=0`,`53`; `days=null`; `days=` → all **422**. Plus a regression lock that omitting `days` yields `30` (L9).
Continuing from Phase 13.2 item 33 — completing the remaining required tests, then the consolidated contract.

33. **Repository mismatch / unauthorized workspace access (analytics)** — with a repository whose `workspace_id` differs from the path `workspace_id`: all 5 analytics endpoints → **404 `"Repository not found in this workspace"`**, and **no Redis key is ever read or written** (assert the cache key list is empty). Also assert the access check happens *before* the cache read (cross-tenant cache isolation).
34. **Cache hit** — pre-seed a value under `analytics:overview:{repo}:days:30` → service returns it with `cached: true` and the repository is **never** called (`test_analytics.py:116-159` already does this at the service layer; add a route-level test asserting the `cached` field survives serialization).
35. **Cache miss** — computed, persisted with TTL 900, `cached: false` (`test_analytics.py:162-205` covers the service; add TTL + key-name assertions).
36. **Cache invalidation** — the 5 prefixes asserted in exact order (`test_analytics.py:431-451`); **add**: invalidation occurs **after commit**, not before (L3); every `days`/`weeks` variant is removed (`prefix*` glob); a second analytics call after invalidation recomputes with `cached: false`.
37. **Redis unavailable** — `GET` fails → 200 with `cached: false` (recording: `test_redis_soft_fail_on_connection_error`); `SET` fails → 200, uncached; `delete_prefix` fails → invalidation is a no-op and the request still succeeds; Redis down during `POST /sync` → the in-process fallback runs and the job still reaches a terminal state.
38. **Empty-data tests** — repository with 0 PRs returns well-formed payloads for all 5 endpoints; workspace with 0 repositories returns `[]`; workspace with no syncs returns `[]`; untracked repo detail → 404.
39. **Boundary tests** — `weeks=1` and `weeks=52` (single bucket / 52 buckets); `days=1` and `days=365`; `per_page=1` and `per_page=100`; `page=1` with `total=0`; a 5001-PR repository → sync silently truncates (L11, asserted so the regression is visible).
40. **Serialization** — `week_start`/`day` carry **no timezone designator** in the JSON (L16) — a contract-lock test so a future fix is a conscious decision.

**Verdict:** the unit suite protects orchestration and DTO shape well, but **the SQL layer is entirely unverified** (items 21–32, 38–39). If any of those fail against real PostgreSQL, the analytics contract in this document changes — run them before binding the frontend types.

---

# PHASE 14 — FRONTEND INTEGRATION CONTRACT

> One consolidated, implementation-ready summary. Detail lives in Phases 2–13; this section is the checklist the frontend implements against. Items marked **⚠️** are backend defects/limitations with a linked loophole ID.

## 1. Base URL
- Local dev: `http://localhost:8000`
- Production: `https://github-dashboard-xvea.onrender.com` (Render; `render.yaml` is the deploy blueprint)
- API prefix: **`/api/v1`** for everything except `GET /health`.
- Unauthenticated extras: `/docs`, `/openapi.json` (use it to regenerate types), `/redoc`.
- Vite dev proxy: point `/api` at the backend, or call it cross-origin — both work.

## 2. Authentication
- **Supabase Auth → `Authorization: Bearer <access_token>`** on every request except `/health` and `POST /api/v1/webhooks/github` (HMAC-signed by GitHub).
- Scheme matching is case-insensitive (`bearer` works).
- **Refresh policy:** on `401 {"detail":"Invalid or expired token"}` → `supabase.auth.refreshSession()` → retry **once**; on `401 {"detail":"Not authenticated"}` or `"Invalid Authorization header"` → sign out, do **not** refresh.
- **⚠️ L8:** if the backend's Supabase env is misconfigured you get **500**, not 401. Treat 500 on authenticated routes as "possibly an auth/backend misconfiguration" in the error UI.
- Verified claims: `sub`, `exp`, `iss`, `aud="authenticated"`; identity fields come from `email`, `user_metadata.full_name|name`, `user_metadata.avatar_url|picture`.

## 3. Required headers
| Header | When | Value |
|---|---|---|
| `Authorization` | all product endpoints | `Bearer <supabase-access-token>` |
| `Content-Type` | all bodies | `application/json` |
| `X-GitHub-Event` | webhook only | event name (**missing → 422**) |
| `X-Hub-Signature-256` | webhook only | `sha256=<hmac>` |
| `Origin` | automatic | must be in `CORS_ORIGINS` (currently only `http://localhost:5173` and `http://127.0.0.1:5173`) — **⚠️ the production frontend origin must be added via `CORS_ORIGINS` before deploy** |

## 4. Complete endpoint list
```
GET     /health                                                              public
GET     /api/v1/me                                                           user
POST    /api/v1/workspaces                                                   user
GET     /api/v1/workspaces                                                   user
GET     /api/v1/workspaces/{workspace_id}                                    member
GET     /api/v1/workspaces/{workspace_id}/github/install-url                 OWNER
POST    /api/v1/workspaces/{workspace_id}/github/connect                     OWNER
DELETE  /api/v1/workspaces/{workspace_id}/github/disconnect                  OWNER
GET     /api/v1/workspaces/{workspace_id}/github/repositories                member
POST    /api/v1/workspaces/{workspace_id}/repositories/track                 OWNER
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked               member
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}          member
DELETE  /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}          OWNER
POST    /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync     OWNER
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync-jobs/{job_id}  member
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/sync-jobs          member
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/pull-requests       member
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/overview   member
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/throughput member
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/activity   member
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/cycle-time-trend member
GET     /api/v1/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics/authors    member
POST    /api/v1/webhooks/github                                              GitHub HMAC
```
Full request/response shapes: **Phase 2**. TypeScript types: **Phase 11 (normative)**.

## 5. Request shapes (exact)
| Endpoint | Body / Query |
|---|---|
| `POST /workspaces` | `{"name": string}` (1–255) |
| `POST …/github/connect` | `{"installation_id": number}` (> 0) |
| `POST …/repositories/track` | `{"owner": string, "repo": string}` (each 1–255) |
| `GET …/github/repositories` | `page` (≥1, d.1), `per_page` (1–100, d.100) |
| `GET …/sync-jobs` | `limit` (1–50, d.10) |
| `GET …/pull-requests` | `state` (`open`/`closed`/omit), `page` (≥1, d.1), `per_page` (1–100, d.50) |
| `GET …/analytics/overview` | `days` (1–365, d.30) — **all-time unreachable ⚠️ L9** |
| `GET …/analytics/throughput` | `weeks` (1–52, d.8) |
| `GET …/analytics/activity` | `days` (1–365, d.30) |
| `GET …/analytics/cycle-time-trend` | `weeks` (1–52, d.12) |
| `GET …/analytics/authors` | `days` (1–365, d.30) |
| `POST …/sync`, `DELETE …/tracked/{id}`, `DELETE …/github/disconnect` | no body |
| `POST /webhooks/github` | raw GitHub JSON body |

## 6. Response shapes (exact)
`UserResponse`, `WorkspaceSummary`, `WorkspaceResponse`, `GitHubRepositoryResponse`, `RepositorySummary`, `RepositoryResponse`, `SyncJobCreateResponse`, `SyncJobResponse`, `PullRequestListResponse{items,total,page,per_page}`, and the five analytics responses are defined verbatim in **Phases 2 + 11**. Critical wire facts:
- List endpoints (`workspaces`, `github/repositories`, `tracked`, `sync-jobs`) return a **bare array** — no envelope, no `total`.
- `week_start`/`day` are **timezone-less** naive UTC ISO strings → **append `Z` before `new Date()`** ⚠️ **L16**.
- `timestamptz` fields (`created_at`, `merged_at`, …) **do** carry an offset — the two timestamp families are inconsistent.
- `merge_rate_percentage`, all cycle-time fields, `description`, `author_login`, `merged_at`, `closed_at`, `error_message`, `started_at`, `completed_at` are nullable; everything else is required.
- `state` is only `"open"|"closed"`; **"merged" ⇔ `merged_at !== null`**.
- Analytics arrays are **always exactly `weeks`/`days` long** (dense, zero-filled).
- Activity has **no `is_partial`** ⚠️ L15; throughput and cycle-time-trend flag the last item only.
- Authors are capped at **20 rows**, unindicated ⚠️ L12.

## 7. Error handling
| Status | Meaning | `detail` shape |
|---|---|---|
| 400 | business precondition (not connected, unverifiable installation) | string |
| 401 | missing/malformed/invalid token | string (`Not authenticated` / `Invalid Authorization header` / `Invalid or expired token`) |
| 403 | not a member (`You do not have access to this workspace`) or not owner (`Owner permissions required for this action`) | string |
| 404 | workspace/repository/sync-job not found **in this scope** (never leaks existence) | string |
| 422 | validation (bad UUID, out-of-range query, bad body, missing webhook header) | **array** of `{type,loc,msg,input,ctx?}` |
| 429 | GitHub primary rate limit (`track`, `github/repositories`) | string |
| 502 | GitHub authentication failure | string |
| 500 | unhandled: `GitHubAPIError`, `GitHubAppConfigError`, `IntegrityError` (L4, L6, L7, L8), or a real crash | string |

Always branch on `Array.isArray(body.detail)`.

## 8. Workspace flow
Supabase sign-in → `GET /workspaces` (empty ⇒ `POST /workspaces`, store `workspace_id`) → `GET /workspaces/{id}` → derive role by probing `GET …/github/install-url` (**L1**). Persist `workspace_id`; never persist `github_installation_id` as the connection truth — always re-read `is_github_connected`.

## 9. GitHub connection flow
`GET …/github/install-url` (OWNER) → full-page redirect to `install_url` (state = workspace_id) → **the callback lives on your frontend** (backend has no callback route; **NOT VERIFIED IN CODEBASE** where the GitHub App's Setup URL points) → parse `installation_id` + `state`, **verify `state === selected workspaceId`** (L20) → `POST …/github/connect` → `WorkspaceResponse` with `is_github_connected: true`. Errors: 400 (unverifiable), **500** (rate limit / already-linked / misconfig, L6/L7). Handle `connection_stale` on later 400/502s (L19 — no installation-lifecycle webhooks).

## 10. Repository flow
`GET …/github/repositories` (available) ⟶ join on **`full_name`** against `GET …/repositories/tracked` (tracked; gives `repository_id`) → `POST …/repositories/track` (OWNER; 201 `RepositoryResponse`) → disable the button while pending (L7). **Tracking does NOT sync** — analytics stay empty until step 11.

## 11. Sync flow
`POST …/sync` (OWNER) → `202 {job_id, status:"queued"}` → poll `GET …/sync-jobs/{job_id}` at **2 s → 5 s after 15 s, abort at ~120 s** → terminal `completed`/`failed` → invalidate all 5 analytics query keys. `total_synced` = **"PRs processed"** (not new; capped at 5000, L11). ⚠️ **L2: no worker process is deployed anywhere → production jobs stay `queued` forever.** ⚠️ L10: no dedup — guard the button with `GET …/sync-jobs?limit=1`. A 404 mid-poll means the repo was untracked (cascade).

## 12. Analytics flow
All 5 endpoints, member role, identical pipeline: access check → Redis (TTL 900 s, `cached` flag) → SQL → response. Meanings and edge cases: **Phase 7**. Overview/authors window on **creation date**; throughput/cycle-time-trend on **merge date** (L17 — label accordingly). Cycle-time `null` ⇒ render a gap, never 0. No cache-bypass mechanism exists; freshness comes only from sync/webhook invalidation + frontend refetch.

## 13. Cache / refetch behaviour
- Backend: Redis cache-aside, TTL **900 s**, keys `analytics:{metric}:{repository_id}:{days|weeks}:{value}`; all 5 prefixes invalidated on sync completion and on every webhook event for that repo.
- **⚠️ L3:** invalidation happens **before commit** → up to 15 min of stale data repopulated by a concurrent read. Frontend mitigation: refetch after a sync completes and keep `staleTime` low; you cannot force a bypass.
- Frontend: `staleTime` 30–60 s, `refetchOnWindowFocus: true`, optional 60–120 s background interval while a dashboard is open; never blanket-retry mutations.

## 14. TypeScript types
See **Phase 11** — normative, generated from `app/schemas/*.py` with no invented fields.

## 15. Query-key recommendations
See **Phase 10** — full key map, `enabled` dependencies, refetch triggers, polling intervals, and invalidation graph.

## 16. UI state requirements
See **Phase 12** — session, workspace, **role (derived by probing, L1)**, GitHub connection (incl. `install_pending` across a full-page navigation via `sessionStorage`), repository, sync (incl. `sync_stuck` and `untracked_midflight`), analytics (incl. `cached`, `empty`, `refetching`), plus the empty-state decision table.

## 17. Known backend limitations
1. No role in any response (L1) · 2. No worker deployed (L2) · 3. Stale-cache race (L3) · 4. Rate limits/API errors → 500 (L4) · 5. Webhook verification fails open (L5) · 6. Installation ID globally unique (L6) · 7. Track race (L7) · 8. Auth misconfig → 500 (L8) · 9. All-time window unreachable (L9) · 10. No sync dedup (L10) · 11. 5000-PR silent ceiling (L11) · 12. 20-author cap (L12) · 13. `state` unvalidated (L13) · 14. Missing analytics indexes (L14) · 15. No activity `is_partial` (L15) · 16. Timezone-less bucket strings (L16) · 17. Inconsistent window bases (L17) · 18. Fire-and-forget task (L18) · 19. No installation-lifecycle webhooks (L19) · 20. Unsigned install `state` (L20) · 21. **SQL layer has zero test coverage** · 22. `/users`, `/people`, `/github`, `/repositories`, `/issues`, `/pull-requests`, `/work`, `/sync` are empty placeholder routers — no member management, no workspace rename/delete, no org-wide analytics · 23. `.env` with live credentials is committed to the repo.

## 18. Backend issues that MUST be fixed before frontend integration
| Priority | Item | Why it blocks |
|---|---|---|
| **P0** | **L2** — deploy a worker (`render.yaml` background service + docker-compose `worker`) | every sync-dependent flow is dead in production |
| **P0** | **L16** — emit `Z` on `week_start`/`day` (or attach UTC tzinfo) | wire-format change; breaks date rendering everywhere; must land before types bind |
| **P0** | **L1** — expose `role` on `WorkspaceResponse`/`WorkspaceSummary` | cannot build any owner/member UI |
| **P1** | **L3** — invalidate analytics cache *after* commit | dashboard shows stale data for up to 15 min post-sync |
| **P1** | **L9 + L15** — decide `days` all-time semantics; add `is_partial` to `ActivityTrendItem` | both are **response-schema decisions**; changing them after the frontend binds is a breaking change |
| **P1** | **L4 + L5** — map `GitHubAPIError`/`GitHubAppConfigError`/secondary limits to 429/502/503; fail closed on unset webhook secret | correctness + security |
| **P2** | **L6** — installation-sharing model (allow N workspaces per installation, or 409) | connect flow 500s for a second workspace |
| **P2** | **L8** — catch `TokenVerificationError` → 401/503 | distinguishes "bad token" from "broken backend" |
| **P2** | **Phase 13.2 items 21–32** — write the analytics/SQL tests against PostgreSQL | the contract in this document is currently unverified at the SQL layer |

## 19. Backend issues that can safely be deferred
L7 (button guard suffices) · L10 (frontend guard + optional 409 later) · L11 (warn at `total_synced === 5000`) · L12 (label "Top 20") · L13 (only send `open`/`closed`) · L14 (indexes, once real repos get large) · L17 (precise axis/window labels) · L18 (frontend timeout) · L19 (surfaced as "connection may be revoked") · L20 (verify `state` client-side) · member invite/management, workspace rename/delete, commits/issues/releases/work domain features (all unimplemented placeholders).

## 20. Recommended integration order
1. **Backend P0s first** (L2, L16, L1) — nothing else is worth building against a contract that changes.
2. Auth + `/me` + workspace list/create (Phase 3, 8.1–8.3).
3. Role probing + GitHub connect flow incl. callback page (Phases 4, 9).
4. Repo picker + track + `repositories/tracked` join (Phases 4–5, 9).
5. Sync trigger + polling + stuck-state handling (Phase 5, 11 — after the worker exists).
6. PR table (Phase 9 #17).
7. Analytics: overview → throughput → activity → cycle-time-trend → authors, in that order (Phase 9 #1–5), with the date/`Z` helper centralised.
8. Cache/refetch wiring and background refresh (Phases 10, 13).
9. Empty/error/polish states using the Phase 12 tables.

---

## Audit summary

- **Verified end-to-end:** all 23 routes (enumerated at runtime), every Pydantic DTO, every service→repository→SQL path, the Redis cache-aside pipeline, the webhook pipeline with all 5 cache-invalidation prefixes, the sync job state machine, the Supabase verification boundary, the 4 migrations, and the full test suite (79 unit tests passing; integration suite requires a Postgres test DB).
- **20 numbered loopholes (L1–L20)**, each with severity, exact file/function, root cause, concrete failure example, frontend impact, required fix, and whether a frontend workaround exists.
- **Three P0 blockers before frontend integration:** the missing worker process, the timezone-less bucket timestamps, and the missing role in responses.
- **Three P1 schema decisions to make now** (all-time `days`, activity `is_partial`) because they are breaking changes once the frontend types bind.
- **Biggest unverified risk:** the analytics SQL layer (`percentile_cont`, `date_trunc`, `ON CONFLICT`) has **zero test coverage** — the Phase 13.2 test list is the safety net for the contract above.

**Nothing in the repository was modified.** All read-only inspection, `pytest`, and in-process `TestClient` probes only. If you'd like, the natural next step is to turn the Phase 13.2 required-test list and the P0 backend fixes into an actionable plan — say the word and I'll draft that plan (still without touching code until you switch to Act mode).