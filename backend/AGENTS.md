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
- Grid image tools bind the authenticated Chat subject at construction and
  refresh the delegated token immediately before each image request, including
  batch items. The image endpoint and key must match Chat's configured Grid
  account-exchange service; other providers receive no Grid token. Missing user,
  mismatched service key, or exchange failure rejects before image dispatch.
  A Grid key paired with a noncanonical image endpoint also rejects; it must
  not fall through to the generic provider transport without delegation.
  Tokens never live in the shared image-provider credential configuration.
  Delegated Grid image generation uses a request-local OpenAI SDK client with
  automatic retries and redirects disabled: an uncertain POST must not create
  another paid job or forward identity to a redirect target. The token belongs
  only in HTTP headers, never the generation JSON body.
  The local HTTP stand-in test exercises the actual provider and SDK, including
  lost responses and 429/5xx errors; it is not a funded Core billing canary.
  Grid image edits remain disabled in Chat until their transport, recipe and
  billing lifecycle are verified. Other providers' image editing is unchanged.
- `onyx/db/grid_image_requests.py` and Alembic `a1f092c7d8e3` back the candidate
  Chat image recovery flow (not deployed). `image_recovery.py` binds the owner,
  service identity and tenant; `process_message.py` supplies the reserved
  assistant-message ID, never a user-message ID or an LLM-supplied identifier.
  Tool placement and image index distinguish independent items and models.
  One committed owner/assistant-message/slot claim permits one submission;
  repeated claims only return the existing receipt. A recovery 404 never
  permits redispatch. Claims lock the assistant row: an earlier LLM-turn group
  blocks new groups even after settlement, so asset-download failures cannot
  cause an LLM retry to buy more images. Parallel tool tabs and batch items in
  the same turn remain independent. New generations require a new user request.
  Use dedicated short-lived sessions; no network I/O in a
  journal transaction. Core remains the authoritative billing ledger.
  A new submission requires Core's account charging flag to be true; unbilled
  preview accounts reject before dispatch. Successful tool output requires a
  validated, settled Core recovery result, including its cost. Assets are
  fetched through the SSRF-safe client with redirects off, a 20 MiB bound and
  SHA-256 verification. A missing/uncertain response never grants another POST.
  `GET /api/grid/images?message_id=...` lists only the signed-in owner's journal;
  `GET /api/grid/images/{request_id}` recovers it without submitting work.
  Both return private no-store metadata. The `/content` subroute serves only
  owner-checked, integrity-verified raster bytes, with `nosniff` and no-store;
  `download=true` selects attachment disposition. It never generates an image.
  The candidate browser UI discovers receipts for visible signed-in messages,
  including error responses, and recovers original images after reload. Funded
  production/account-linking and full Chat deployment canaries remain outstanding.
  Journal rows follow Chat user/message deletion; Core's billing records do
  not. Production code rollback must retain a populated journal schema.
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
- Image journal: set `AIPG_TEST_POSTGRES_URL` to a disposable PostgreSQL instance
  and run the `test_grid_image_journal.py` and `test_grid_image_recovery.py`
  modules under `backend/tests/external_dependency_unit/db/`.
  Tests apply the actual migration in unique temporary schemas, exercise real
  concurrent claims and terminal writes, then drop those schemas. Hosted
  database CI invokes this explicitly; skipped tests are not concurrency proof.
  Recovery tests use real Postgres and SDK HTTP against a local Core stand-in,
  including killing a submitting subprocess after the POST was received. They
  are not evidence of production Core billing or a real worker generation.
- Integration: use managers/fixtures under `backend/tests/integration`.
- `scripts/verify_grid_billing_auth.py` runs against the actual packaged
  application with basic auth and unmodified dependencies. Image recovery and
  account reads must reject unauthenticated callers; recovery has no POST
  route. Hosted image CI runs this with networking disabled, no credentials,
  and the ASGI lifespan skipped. It does not prove application startup,
  signed-in ownership, or funded billing.
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
