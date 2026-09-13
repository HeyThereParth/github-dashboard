---
name: feature-planning
description: Plans features before implementation with emphasis on understanding and maintainability.
---

# Feature Planning

Before implementing a significant feature:

## 1. Understand

Explain what the feature actually needs to accomplish.

## 2. Requirements

Identify:

- inputs
- outputs
- business rules
- edge cases
- failure cases

## 3. Architecture

Identify which components are affected.

## 4. Design

Propose a simple implementation.

## 5. Alternatives

Mention important alternatives only.

Do not overwhelm the developer with unnecessary options.

## 6. Data

If data storage changes, explain:

- schema
- indexes
- relationships
- consistency concerns
- migration implications

## 7. API

If an API changes, explain:

- endpoint
- request
- response
- status codes
- validation
- errors

## 8. Testing

Define what should be tested.

## 9. Implementation Plan

Produce a small sequence of implementation steps.

Only after planning should implementation begin.