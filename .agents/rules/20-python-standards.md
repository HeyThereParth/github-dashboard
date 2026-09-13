---
trigger: always_on
---

---
name: python-standards
description: Python-specific engineering practices.
---

# Python Standards

## Style

Follow modern Python conventions.

Prefer readable Python over clever Python.

Use meaningful names.

Avoid unnecessary abbreviations.

---

## Type Hints

Use type hints for:

- public functions
- important interfaces
- complex data structures
- service boundaries

Do not add meaningless types simply to satisfy a checker.

---

## Functions

Prefer small functions with clear responsibilities.

If a function becomes difficult to explain in one sentence,
consider whether it has multiple responsibilities.

---

## Data Models

Use explicit models for structured data.

Do not pass loosely structured dictionaries throughout the application
when a proper model would make the contract clearer.

---

## Async

Do not use async simply because the framework supports it.

Understand:

- synchronous execution
- asynchronous execution
- event loops
- blocking operations
- concurrency

Before introducing async abstractions.

Never perform blocking operations carelessly inside asynchronous code.

---

## Exceptions

Catch exceptions only when you can meaningfully handle them.

Do not use exceptions as normal control flow unless appropriate.

Preserve useful error context.

---

## Imports

Keep imports organized and avoid circular dependencies.

When circular dependencies appear, investigate the architecture
rather than applying hacks immediately.

---

## Testing

Prefer testing behavior rather than implementation details.

Tests should cover:

- normal behavior
- invalid input
- edge cases
- expected failures
- important business rules