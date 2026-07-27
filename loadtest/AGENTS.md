# AIPG Chat Load Tests

## Purpose

Isolated Locust workloads for chat, retrieval, research, long-conversation,
and disconnect behavior, plus a deterministic mock LLM and observability
assets. This is intentionally not part of the backend's uv workspace.

## Ownership

- `scenarios/` - user workloads and collapse-point shapes.
- `onyx_client/` - vendored client and stream parsing used under gevent.
- `mock_llm/` - deterministic OpenAI-compatible test provider.
- `tests/` - contracts for the mock and workload helpers.
- `k8s/`, `dashboards/` - distributed runners and monitoring assets.

## Local Contracts

- Never run load tests against production without explicit approval for the
  exact target, user count, ramp, duration, credentials, and abort threshold.
- Use dedicated, least-privilege test credentials and synthetic content. Never
  place real API keys or user data in commands, fixtures, manifests, or reports.
- Keep this uv project isolated and do not import `onyx.*`; Locust's gevent
  dependency constraints must not leak into the backend environment.
- A stream counts as successful only after the expected terminal event. Retain
  separate metrics for intentional disconnects and provider/application faults.

## Work Guidance

- Prefer the mock LLM for repeatable application and infrastructure tests.
- Bound every run by duration and document model profile, scenario mix, target,
  and concurrency with the results.
- Update `README.md` when metrics, environment variables, scenario semantics,
  or mock-provider behavior changes.

## Verification

- Run `uv sync` from `loadtest/`.
- Run `uv run pytest tests/ -q`.
- Smoke the mock with `uv run uvicorn mock_llm.app:app --port 8001` and use a
  one-user, short-duration local Locust run after protocol changes.

## Child DOX Index

No child guides are currently required; this file owns the complete isolated
load-test project.
