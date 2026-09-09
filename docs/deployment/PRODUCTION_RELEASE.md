# Chat production release

Status: current operator contract for the Docker Compose deployment of
`aipg.chat`.

## Release rules

- Build from an exact pushed commit, never a dirty checkout.
- Extract each source archive into a new immutable release directory.
- Preserve tracked file/directory permissions while extracting (GNU tar
  `--same-permissions`). A private operator umask must not turn image assets
  into root-owned `0700` directories in the Docker context. Keep the enclosing
  release/audit directories private and copy secrets separately with restrictive
  permissions; do not recursively relax a release containing `.env` files.
- Copy the existing production `.env` at deploy time; never place it in the
  archive or Git.
- Set `IMAGE_TAG` to a unique tag and `ONYX_VERSION` to the release commit's
  short SHA before building. Both the backend `/api/version` response and the
  web footer must report that SHA.
- Replace only `api_server`, `background`, and `web_server`. Do not recreate the
  database, Redis, object storage, search, model servers, or Nginx as part of an
  application release.
- Keep the previous release directory and images until the new release passes
  every health check.

## Build and validate

From the new release's `deployment/docker_compose` directory:

```bash
docker compose -f docker-compose.prod-no-letsencrypt.yml config --services
docker compose -f docker-compose.prod-no-letsencrypt.yml build api_server web_server
```

Before deployment, inspect both image tags and run a one-shot backend import
smoke for authentication-critical packages. At minimum verify `eth-account`,
`pydantic`, `starlette`, and `cryptography`, plus the `ONYX_VERSION` environment
value in both images.

Also start the built web image as its default unprivileged user with networking
disabled. Request `/auth/login` and every referenced JavaScript asset through
container-local HTTP, require `200`, and verify it stays running. A successful
Next build alone does not prove that its runtime user can read public assets.
Stop and remove the disposable smoke container afterward.

Compose configuration validation requires `.env.nginx` even when replacing only
the application services. Preserve that file from the running Nginx container's
labelled working directory in both candidate and rollback directories. Do not
recreate Nginx or change its configuration as a side effect of this preparation.

## Deploy

### Grid image billing gate

Delegated image generation uses a request-local SDK client without retries or
redirects. The HTTP stand-in regression proves one POST for 429/5xx/lost-response
outcomes and header-only user identity; it does not prove a paid Core lifecycle.
Grid image edits are disabled in Chat pending their own verification.
A Grid key at a noncanonical image endpoint fails closed instead of bypassing
delegation through the generic provider transport.

Before enabling paid images in Chat, verify that the configured image endpoint
and service key match the canonical Grid identity exchange, then run a funded
tool call with the authenticated user's account and reconcile its reservation,
settlement and reward eligibility. An uncertain response must not be presented
as a free failure or automatically regenerated. Keep this path out of the paid
launch until its complete browser-to-Core recovery behavior is verified.

The pending journal migration `a1f092c7d8e3` adds owner/message-scoped request
receipts and a one-submission claim guard. The candidate now wires the tool to
the server-reserved assistant message and image slot, commits before POST and
sends the UUID as Core's progress/client reference. It persists validated Core
terminals and exposes owner-checked list/recovery endpoints under `/api/grid/images`.
One assistant response may open one image tool-turn group, including parallel
tool tabs and batch items. Later LLM-turn groups reject even after settlement:
a failed asset download must recover the paid result, not buy another image.
An account still in unbilled preview mode is rejected before generation.
Real Postgres plus a local HTTP stand-in cover a killed submitting process,
lost replies, repeated calls, partial batches and foreign-owner denial.
The candidate browser now discovers receipts for visible authenticated messages
and error responses. Unknown results offer a read-only check, completed results
can be reopened/downloaded through the owner-checked `/content` subroute, and
normally displayed images keep their originals collapsed until requested.
Receipt caches are separated by Chat user; shared messages do not activate
private receipt discovery. No recovery control calls the generation API.
Still required: real funded Core/worker and account-linking canaries, including
the complete deployed Chat stream, crash/reload and partial-batch paths. Local
component tests and mocked browser responses do not prove those production gates.
A new explicit assistant generation is a new paid intent; it is not a way to
recover an earlier request.
If deployed later, migrate before serving the new code. Keep the additive
journal on rollback; its downgrade refuses nonempty data.

#### Restored-database rehearsal (2026-09-09 UTC)

Candidate `93fb5a7aa757cac60edcde55a7cfcdfb650caac4` was rehearsed against a
private restore of the live PostgreSQL 15 database, not the live database:

- Production started and remained at application `4ff336d32d` and Alembic
  `01c63968ff8f`. The API container ID and start time were unchanged.
- The custom-format backup was 4,082,000 bytes; SHA-256:
  `d87393842c43bf6b618c1fcb2554f68823c2645d5b478ec21aa2e05127f5bd0c`.
- The restore contained 136 existing public application tables. The real
  Alembic `upgrade head` reached `a1f092c7d8e3`; a second upgrade was a no-op.
  Row counts and content fingerprints of all 136 pre-existing tables matched
  before and after both upgrades. The new journal had zero rows.
- The one-shot migration used the current production backend image's
  dependencies with the exact candidate backend source mounted read-only;
  temporary directories and logging were writable tmpfs. This is migration
  compatibility evidence, not a deployment of the candidate application image.
- The scratch database and temporary database-credential file were removed.
  The backup, configuration snapshot and successful `rehearsal-2/proof.json`
  remain in the private `chat-93fb5a7aa7` release-check directory. Never commit
  the backup or credential-bearing snapshots/logs.

This rehearsal does not replace a fresh pre-cutover backup, current-head CI,
the full application build, or funded end-to-end billing canaries. The later
lazy-import/formatting cleanup does not change this migration.

#### Packaged runtime rehearsal (2026-09-09 UTC)

Both Linux/amd64 application Dockerfiles built successfully from pushed commit
`65c656aa51d40c60e739db78ed1de93e2d6a9167`, using its clean Git archive rather
than the operator worktree. The archive was 20,077,374 bytes; SHA-256:
`d46057088f283d72dc1735a63e27a2fe69524973f20c21fda31175749679e7ea`.
The separate builder was capped at two CPUs and 8 GiB RAM and received no
production environment or credentials. These are operator-built rehearsal
images, not published CI release artifacts or a production deployment.

| Candidate image | Docker image ID |
| --- | --- |
| `aipg-chat-backend:billing-65c656aa51` | `sha256:468668c7cdc75be0fce102919f6027183702b44becd32ff593676c3426f67641` |
| `aipg-chat-web:billing-65c656aa51` | `sha256:9304bb275de81134a92fee9b693a6a66f7722863abf73dc168bc19fe0a55bd71` |

- Both images carry the exact source revision label and `ONYX_VERSION=65c656aa51`.
  Ten packaged backend source files, including the image journal migration,
  matched the archive's SHA-256 hashes.
- The backend passed authentication-package imports and full application
  route/auth checks as UID 1001 with networking disabled. Native basic auth
  returned `403` with the unauthenticated error for account, image-list,
  recovery and content reads. POST to recovery returned `405`.
  No authentication dependency was mocked; ASGI lifespan was intentionally
  skipped. This does not establish database-backed startup or signed-in access.
- The frontend passed the complete Next production build, including TypeScript
  and route generation. A temporary network-isolated server returned `200` for
  the login page, all 32 referenced JavaScript assets and the PNG logo. Its API
  backend was deliberately unavailable; rendering the page does not prove
  Google/wallet login, account attribution or generation. The server was removed.
- Production API, background and web containers remained on `4ff336d32d`, with
  their original 2026-08-29 start times. No live application migration,
  generation, charging activation or payout action was performed.

The reusable [packaged-auth check](../../backend/scripts/verify_grid_billing_auth.py)
now runs in hosted backend-image CI. It supplements, not replaces, database,
ownership, funded recovery and full deployed application canaries. The private
`chat-65c656aa51` release-check directory retains build logs and
`build-proof.json`; it contains the exact tested image IDs and source hashes.
The subsequent auth-smoke/CI/docs changes do not alter the packaged application
source or migration. Revalidate current-head checks and release provenance
before any cutover; this rehearsal does not waive queued inherited checks.

### Application activation

```bash
docker compose -f docker-compose.prod-no-letsencrypt.yml \
  up -d --no-deps api_server background web_server
```

Docker Compose may assign the recreated backend a different container IP.
The long-running Nginx container resolves its upstream at configuration load,
so validate and reload Nginx immediately after the application containers are
ready:

```bash
docker exec onyx-nginx-1 nginx -t
docker exec onyx-nginx-1 nginx -s reload
```

Skipping this reload can leave public `/api/*` requests returning `502` while
the backend itself is healthy.

## Health gates

Do not declare the release healthy until all of these pass:

1. `api_server`, `background`, and `web_server` use the new immutable image tag
   and remain running.
2. Recent logs contain no traceback, fatal, panic, or unhandled error.
3. `/`, `/auth/login`, `/api/auth/type`, `/api/settings`, and `/api/version`
   return `200` through the public origin.
4. `/api/version` and the signed-in footer show the expected release SHA.
5. Google login remains offered and an existing signed-in session can load its
   canonical Grid account and balance.
6. An unauthenticated request to `/api/grid/account` remains denied.
7. Grid charging stays at its intended rollout state; application deployment
   must never silently change the Core charging flag.

## Rollback

The old API startup command runs `alembic upgrade head`; retaining an additive
table is not enough when the old image cannot recognize the new revision ID.
For rollback from `a1f092c7d8e3` to the `4ff336d32d` application, supply the
reviewed `a1f092c7d8e3_grid_image_recovery_journal.py` migration file as a read-only
bind mount at the same `/app/alembic/versions/` path using a rollback-only Compose
overlay. The migration was verified compatible with the old image dependencies.
Do not stamp backwards, downgrade the journal, or drop recovery records.

Run `up -d --no-deps --no-build` from the previous immutable release directory
with that overlay, then validate and reload Nginx after API startup completes.
Repeat the public health gates and retain the failed release for diagnosis.

### September 9 release exception and first-attempt findings

The maintainer approved releasing merged commit
`085e7394b50b2e72ee8a9181a073412490324918` using the passing AIPG-hosted unit,
type, PostgreSQL, HTTP, Jest and packaged-auth checks. The 38 inherited private
runner checks were still queued, not passed. This is a release-specific exception,
not permission to waive funded browser/worker canaries or enable global billing.

The first activation exposed root-owned unreadable web assets from archive
extraction under umask `077`. The web container restarted; the application was
rolled back. That rollback also exposed the missing Alembic revision dependency
described above. The reviewed read-only migration mount restored the old API;
public `/api/version` again returned `4ff336d32d`. No paid generation ran during
this attempt. Corrected packaging uses distinct `grid-085e7394b5-r2` image tags
and must pass the new web-runtime gate before another cutover.

### September 9 corrected activation and paid canary

The corrected release is deployed from the same reviewed merge commit using
`grid-085e7394b5-r2` backend/web image tags. Before cutover, the web image ran as
UID 1001 with networking disabled and returned `200` for login and all 22
referenced JavaScript assets. A fresh database backup was restored to scratch;
the additive journal migration was applied twice and all 137 restored tables
retained their fingerprints. The scratch database was then removed.

Only API, background and web application containers were recreated. Database,
Redis, search, storage and model-server containers were preserved; Nginx was
validated and reloaded. Public health gates returned their expected statuses,
including anonymous account access denied with `403`. Existing signed-in
Google access survived and reported the canonical purchased balance. The live
version and signed-in footer both show `085e7394b5`.

The sole configured Krea 2 Turbo image provider was aligned to the existing
server-side Grid endpoint and service credential; no credential was exposed to
the browser. Under a separately approved owner-only Core charging canary:

- A real streamed text reply completed and its reservation/refund reconciled.
- A real image-tool invocation produced one image and exactly one completed
  Chat image journal entry linked to its Grid job.
- Read-only reconciliation showed no double debit, balance discrepancy or
  stranded reservation across these jobs.

This is **not a completed billing-launch signoff**. The broader Core canary
audit raised a separate result-evidence gate, so further paid tests were paused
for a Core fix and repeat proof. Chat image crash/recovery and the remaining
modalities still require their own end-to-end gates. Global charging and payout
resumption remain off. Private release-check artifacts retain image, restore,
container and activation evidence; do not publish account/job IDs or credentials.
