# ADR-0001: Supabase Auth as the external identity provider

- **Status:** Accepted
- **Date:** 2026-09-10

## Context

The application needs authentication, but we do not want to build or maintain
password hashing, session management, JWT issuance, OAuth flows, or
refresh-token handling ourselves. The project requires a third-party
authentication provider, kept separate from GitHub authorization.

## Decision

Use **Supabase Auth** as the third-party authentication provider.

- Supabase issues and owns the tokens; the backend never issues tokens or stores
  passwords.
- The backend verifies the Supabase-issued JWT (JWKS-based, asymmetric keys) and
  maintains its own internal `User`, linked by `auth_provider_user_id`.
- Application authorization (workspace membership) is entirely our concern.

## Consequences

- We never store passwords, tokens, or refresh tokens.
- Supabase-specific verification is isolated behind the `TokenVerifier`
  abstraction (`app/integrations/auth/`), decoupling the rest of the app.
- The provider identity is never our primary key; `users.id` is an internal UUID.
- Swapping the auth provider later means replacing the `TokenVerifier`
  implementation, not the identity/authorization model.
- Alternative considered: HS256 shared-secret verification (discouraged by
  Supabase) and per-request Auth-server verification (network latency/dependency).
  JWKS local verification was chosen as the scalable, offline-testable default.
