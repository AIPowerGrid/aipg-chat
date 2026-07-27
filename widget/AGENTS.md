# AIPG Chat Widget

## Purpose

Embeddable Lit web component for streaming chat on third-party sites. The
compiled widget executes in an untrusted browser and communicates with the
AIPG Chat backend over HTTP and server-sent events.

## Ownership

- `src/services/` - backend requests and stream handling.
- `src/config/` - element attributes and build-time configuration.
- `src/utils/` - Markdown and browser utility code.
- `src/styles/` - Shadow DOM presentation.
- `vite.config.ts` - cloud and self-hosted bundle behavior.

## Local Contracts

- Every credential configured in the widget is public to the page visitor.
  Accept only revocable, rate-limited keys scoped to the minimum chat action;
  never document or support admin, user-session, billing, or general Grid keys.
- Client-visible credentials are not authorization by themselves. The backend
  must enforce origin, persona, tenant, scope, quota, and rate-limit policy.
- Sanitize model-generated Markdown with DOMPurify before inserting HTML.
  Preserve safe URL handling and do not weaken the sanitizer for formatting.
- Bound stream buffers, retries, persisted session data, and rendered content.
  Do not persist secrets or sensitive conversation data without an explicit
  product decision.

## Work Guidance

- Keep the custom-element attribute API backward compatible for embedders.
- Test both cloud and self-hosted build modes when changing configuration.
- Update `README.md` whenever attributes, authentication assumptions,
  endpoints, deployment modes, or bundle setup change.

## Verification

- Run `bun run type-check`.
- Run `bun run build`, `bun run build:cloud`, and
  `bun run build:self-hosted` for configuration changes.
- Exercise a real stream and inspect the built bundle for accidental secrets
  before publishing.

## Child DOX Index

No child guides are currently required; this file owns the widget tree.
