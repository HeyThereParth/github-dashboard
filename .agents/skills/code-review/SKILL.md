---
name: code-review
description: Performs a senior-engineer code review focused on learning and production quality.
---

# Code Review

Review the code as a senior engineer mentoring the developer.

Do not immediately rewrite it.

## Review Order

1. Correctness
2. Bugs
3. Security
4. Architecture
5. Error handling
6. Maintainability
7. Readability
8. Performance
9. Testing

## For Each Important Issue

Explain:

WHAT
What is wrong?

WHY
Why is it a problem?

CONCEPT
What engineering concept is involved?

IMPROVEMENT
What could the developer change?

## Learning Mode

If the issue represents an important concept:

Ask the developer how they would fix it before providing the solution.

## Production Mode

Also identify issues that may not matter in a learning exercise
but would matter in a real production system.

Clearly distinguish:

Learning improvement
from
Production requirement.

## Final Review

Provide:

- Critical issues
- Important improvements
- Nice-to-have improvements
- What was done well
- Recommended next steps