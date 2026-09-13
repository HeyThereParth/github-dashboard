---
trigger: always_on
---

---
name: project-architecture
description: Architectural principles for the backend project.
---

# Architecture

## General

Keep responsibilities separated.

Typical boundaries may include:

API / HTTP layer
    ↓
Application / service layer
    ↓
Data access layer
    ↓
Database

External integrations should have clear boundaries.

---

# API Layer

The API layer should primarily handle:

- HTTP requests
- validation
- authentication/authorization boundaries
- response formatting
- HTTP-specific errors

Business logic should not become concentrated inside route handlers.

---

# Business Logic

Business logic should be independent from HTTP details whenever practical.

Avoid coupling core logic directly to:

- HTTP request objects
- framework-specific response objects
- database implementation details

---

# Database

Database access should have clear boundaries.

Do not scatter database queries throughout unrelated modules.

---

# External Services

External APIs should be isolated behind clear interfaces.

The rest of the application should not need to know every detail
of an external provider.

---

# Architecture Changes

Before making a significant architectural change:

Explain:

1. Current architecture.
2. Current problem.
3. Proposed change.
4. Alternatives.
5. Tradeoffs.
6. New complexity.
7. Migration impact.

Do not introduce architecture simply because it is considered
"industry standard."

Architecture must solve an actual problem.