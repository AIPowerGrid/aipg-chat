# Craft opencode serve migration

## Status

Historical design summary for the migration from per-message `opencode acp`
processes to a long-lived `opencode serve` process. The serve transport is the
current path; `drop-acp-layer.md` documents the cleanup that shipped afterward.

## Why it changed

The per-message process tied agent/session state to one turn, paid process startup
cost repeatedly, and could lose terminal events. A long-lived HTTP/SSE server per
sandbox provides stable session IDs, reconnectable event consumption, explicit
abort, and one provider configuration loaded when the sandbox starts.

## Durable contracts

- `OpencodeServeClient` translates opencode events into the application-owned
  sandbox event schema.
- Each Craft session persists its opencode session ID.
- Kubernetes and Docker managers use isolated network paths and per-sandbox
  server authentication.
- Provider configuration is injected at sandbox creation.
- Disconnect, cancel, timeout, and cleanup remain explicit and idempotent.

See `drop-acp-layer.md` and `preserve-opencode-sessions.md` for current follow-up
behavior. Verify code and tests rather than old line numbers.
