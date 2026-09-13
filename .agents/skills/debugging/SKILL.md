---
name: debugging
description: Guides the developer through systematic debugging instead of immediately fixing errors.
---

# Debugging

Do not immediately fix the bug.

Teach systematic debugging.

## Process

1. Reproduce the problem.
2. Read the complete error.
3. Identify where the error originates.
4. Form a hypothesis.
5. Test the hypothesis.
6. Narrow the problem.
7. Implement a fix.
8. Verify the fix.
9. Add a regression test when appropriate.

## Questions

Ask the developer:

- What do you think is happening?
- Where does the failure originate?
- What evidence supports your hypothesis?
- What would you expect instead?
- What experiment could confirm this?

Only provide the fix directly when requested or when the developer
has exhausted reasonable attempts.

## Important

Never treat error messages as something to simply copy into an AI prompt.

Use them as evidence for reasoning.