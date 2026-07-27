# Craft approvals phase 4: policy management

## Status

Design summary for the policy layer described by `approvals-plan.md`. Verify
current code and tests before treating this phase as shipped.

## Contract

Each registered action has one organization policy:

- `require_approval` creates a live approval and waits for a decision.
- `deny` rejects at the controlled backend/proxy boundary.
- `always_allow` executes silently but writes an auditable decision row.

Unknown or ambiguous actions default to `require_approval`. Policy evaluation
lives in the same trusted interception/orchestration path as enforcement; a
sandbox prompt or tool cannot override it.

Only authorized administrators change organization policy. Every decision path
records the stable action kind, policy result, actor when applicable,
session/run context, and timestamps without storing raw secrets.

## Verification gates

- policy CRUD authorization and tenant isolation
- unknown-action default
- deny and silent-allow enforcement at the backend boundary
- silent-decision audit row
- UI/API agreement on enum values
