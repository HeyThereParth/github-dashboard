---
trigger: always_on
---

---
name: git-and-shipping
description: Git workflow and production shipping standards.
---

# Git

Use meaningful commits.

A commit should represent one logical change.

Avoid commits such as:

"stuff"
"changes"
"fixed things"

Prefer:

"Add GitHub repository service"
"Validate repository webhook payload"
"Add authentication middleware"

---

# Before Committing

Check:

- tests
- formatting
- linting
- accidental secrets
- unnecessary files
- debug statements

---

# Feature Workflow

For significant features use:

1. Understand
2. Plan
3. Implement
4. Test
5. Review
6. Document
7. Commit

---

# Definition of Done

A feature is not considered complete merely because it works locally.

Consider:

- implementation
- tests
- error handling
- security
- logging
- documentation
- configuration
- edge cases
- maintainability

---

# Production Thinking

When appropriate, consider:

- environment configuration
- database migrations
- logging
- monitoring
- failure handling
- timeouts
- retries
- rate limits
- deployment
- rollback

Do not add production complexity without a reason.

Explain why each production concern matters.