# backend - Onyx/AIPG application backend

## Purpose

FastAPI services, PostgreSQL models/migrations, Celery workers, connectors,
search/indexing, LLM providers, AIPG Grid integration, image generation, and the
Craft/build execution control plane.

## Ownership

- `onyx/` - community backend application and AIPG fork integrations.
- `ee/onyx/` - enterprise features and permissions.
- `alembic/`, `alembic_tenants/` - database migrations.
- `tests/` - unit, external-dependency, integration, regression, and shared test
  infrastructure.
- `model_server/` - embedding/reranking and supporting model service.
- `scripts/` - operator and maintenance tools.
- `requirements/` - uv/pip dependency inputs.

## Local Contracts

- Database reads/writes live under `onyx/db` or `ee/onyx/db`; schema changes
  include an Alembic migration and upgrade-path test.
- AIPG Grid provider config lives in `onyx/configs/app_configs.py`; dynamic model
  reconciliation lives in `onyx/llm/aipg`. Empty/unreachable Grid inventory
  must not erase the last known usable provider configuration.
- Grid API keys and provider credentials remain server-side. Status proxies
  return bounded client-safe errors without secrets or upstream internals.
- Every outbound user-facing Grid LLM call carries a short-lived Core user
  token obtained server-side from the bounded `aipg-chat` service key and a
  stable Chat-local subject. Tokens may be cached in bounded backend memory but
  never in a browser or reusable provider configuration. Google ID tokens and
  Core-issued SIWE proofs bind that local subject to Core's canonical account;
  the browser must never choose the app subject. Anonymous callers receive no
  delegated identity. Authenticated clients may read the normalized canonical
  account ID and credit summary through `GET /api/grid/account`; Chat obtains
  both from Core and never derives an account ID locally.
- Chat proxies Core's canonical credit summary and bounded text quote through
  authenticated `/api/grid/account` routes. Quote input uses Grid's
  `o200k_base` counting proxy and the same 32,768-token default reservation
  ceiling as Core; Core's atomic reserve remains authoritative when context
  changes or requests race.
- Use `OnyxError`, typed error codes, and the global error envelope described in
  the root guide; do not add ad-hoc `HTTPException` responses.
- Craft/build routes require the feature gate and authenticated resource
  ownership. Sandbox networks cannot reach data stores, cloud metadata, or host
  secrets. A successful generated build never weakens those boundaries.
- Celery tasks always have expiration and idempotent retry behavior.

## Work Guidance

- AIPG model sync changes span config, DB reconciliation, scheduled task, status
  API, deployment env, and focused tests.
- Craft changes span API authorization, DB ownership, sandbox lifecycle,
  streaming schema, frontend consumer, and cleanup/reclaim behavior.
- Keep generic Onyx changes separable from AIPG-specific provider code.

## Verification

- Unit: `pytest -xv backend/tests/unit`
- External dependency: follow root `.vscode/.env` command and run the focused
  subtree.
- Integration: use managers/fixtures under `backend/tests/integration`.
- Migrations: run `alembic upgrade head`; include tenant migration checks when
  changing enterprise schema.
- Dependency changes: regenerate every export documented in
  `backend/requirements/README.md`, install `default.txt` plus `ee.txt` into an
  isolated Python 3.13 environment with `--no-deps --require-hashes`, and audit
  that exact environment. The patched `msgpack` and `tornado` overrides exceed
  mitmproxy 12.2.3's conservative metadata caps; any change to that set must
  keep `backend/tests/unit/sandbox_proxy` green, including response streaming.

## Child DOX Index

- None at this boundary. Highly specialized subtree READMEs remain binding
  alongside this guide.
