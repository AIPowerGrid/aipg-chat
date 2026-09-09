# Chat production release

Status: current operator contract for the Docker Compose deployment of
`aipg.chat`.

## Release rules

- Build from an exact pushed commit, never a dirty checkout.
- Extract each source archive into a new immutable release directory.
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

## Deploy

### Grid image billing gate

Delegated image generation uses a request-local SDK client without retries or
redirects. The HTTP stand-in regression proves one POST for 429/5xx/lost-response
outcomes and header-only user identity; it does not prove a paid Core lifecycle.
Grid image edits are disabled in Chat pending their own verification.

Before enabling paid images in Chat, verify that the configured image endpoint
and service key match the canonical Grid identity exchange, then run a funded
tool call with the authenticated user's account and reconcile its reservation,
settlement and reward eligibility. An uncertain response must not be presented
as a free failure or automatically regenerated. Durable Chat tool-request/result
recovery remains unproven: the single-shot transport does not make a later
manual retry idempotent. Keep that path disabled for the paid rollout until its
recovery behavior is verified.

The pending journal migration `a1f092c7d8e3` adds owner/message-scoped request
receipts and a one-submission claim guard. Its database helpers have standalone
Postgres tests, but are not yet wired into the image tool or a recovery API.
Remaining integration: supply the server-reserved assistant message and image
slot; commit a claim before POST; send its UUID as Core's progress/client
reference; persist only verified Core terminals; expose owner-checked recovery
without regeneration and restore saved images into Chat. Validate this whole
path, including a killed process and account linking, before paid activation.
If deployed later, migrate before serving the new code. Keep the additive
journal on rollback; its downgrade refuses nonempty data.

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

Run the same `up -d --no-deps` command from the previous immutable release
directory, then validate and reload Nginx again. Repeat the public health gates
and retain the failed release for diagnosis.
