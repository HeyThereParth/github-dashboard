# Database

## Stack

- PostgreSQL via SQLAlchemy 2.0 (async) and the psycopg3 driver.
- Schema managed by Alembic; tables are not auto-created on startup.

## Tables

### users

The internal application user. `id` (UUID) is our primary key — the Supabase
user id is never the primary key.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | primary key |
| `auth_provider_user_id` | varchar(255) | unique; Supabase user id |
| `email` | varchar(320) | nullable, mirrors the provider |
| `name` | varchar(255) | nullable |
| `avatar_url` | text | nullable |
| `created_at` / `updated_at` | timestamptz | server defaults |

### workspaces

The SaaS tenant boundary.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | primary key |
| `name` | varchar(255) | not null |
| `github_installation_id` | bigint | nullable, unique, indexed; links to GitHub App |
| `created_at` / `updated_at` | timestamptz | server defaults |

### workspace_members

Join table between users and workspaces with a role.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | primary key |
| `workspace_id` | UUID | FK → `workspaces.id` (CASCADE), indexed |
| `user_id` | UUID | FK → `users.id` (CASCADE), indexed |
| `role` | varchar(50) | `owner` or `member` |
| `created_at` | timestamptz | server default |

Uniqueness: `(workspace_id, user_id)` — a user has at most one membership per
workspace.

## Relationships

```text
User 1 ──── * WorkspaceMember * ──── 1 Workspace
```

- A user can belong to many workspaces.
- A workspace can contain many users.
- The role model is intentionally simple: `owner` and `member`.

## Conventions

- Repositories are the only layer that touches the database.
- No business logic inside SQLAlchemy models.
- Migrations: `alembic revision --autogenerate` then `alembic upgrade head`.

## Migrations

1. `4663a065fb30`: Initial migration creating `users`, `workspaces`, and `workspace_members`.
2. `b8c3d1e2f4a5`: Adds `github_installation_id` (bigint, unique, indexed) to `workspaces`.


