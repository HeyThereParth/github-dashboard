---
trigger: always_on
---

---
name: engineering-standards
description: General software engineering standards for this project.
---

# Engineering Standards

## General Principles

Prefer:

- simplicity
- readability
- maintainability
- explicit behavior
- small focused components
- clear boundaries
- testability

Avoid:

- unnecessary abstraction
- premature optimization
- clever code
- excessive dependencies
- duplicated logic
- giant functions
- giant modules
- hidden side effects

---

# Before Adding Dependencies

Before adding a dependency:

1. Determine whether the dependency is actually necessary.
2. Check whether the standard library can solve the problem.
3. Consider maintenance cost.
4. Consider security implications.
5. Consider project complexity.

Do not add dependencies simply because they are convenient.

---

# Functions

Functions should generally:

- do one conceptual job
- have clear inputs
- have clear outputs
- avoid unnecessary side effects

Avoid functions that become large collections of unrelated logic.

---

# Error Handling

Do not use broad exception handling unless justified.

Bad:

try:
    ...
except Exception:
    ...

Prefer handling specific failure cases.

Errors should be:

- meaningful
- observable
- appropriately propagated
- safe for users

Do not silently swallow errors.

---

# Configuration

Configuration should not be hardcoded.

Use environment variables or appropriate configuration mechanisms.

Never commit:

- passwords
- API keys
- tokens
- private credentials
- production secrets

---

# Maintainability

Code should be understandable by another developer six months later.

Prefer boring, obvious code over clever solutions.