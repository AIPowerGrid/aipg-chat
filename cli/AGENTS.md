# AIPG Chat CLI

## Purpose

Go command-line and terminal client for querying an AIPG Chat deployment. It
supports interactive chat, script-friendly requests, local configuration, and
an optional SSH-served TUI.

## Ownership

- `cmd/` - command definitions and CLI entrypoints.
- `internal/api/` - authenticated server client and streaming protocol.
- `internal/config/` - local URL, PAT, and preference persistence.
- `internal/tui/` - interactive terminal application.
- `internal/browser/`, `internal/parser/`, `internal/overflow/` - browser
  launches, event parsing, and large-output handling.

## Local Contracts

- Treat PATs and forwarded SSH environment variables as secrets. Never print
  them, put them in command history examples, or include them in diagnostics.
- Preserve non-interactive behavior: machine output goes to stdout, progress
  and errors go to stderr, and commands return the documented exit codes.
- Configuration files must use restrictive permissions and XDG-compatible
  paths. Validate URLs before storing or opening them.
- The SSH server is an internet-facing auth boundary. Preserve host-key
  handling, rate limits, session deadlines, and bounded caches.

## Work Guidance

- Keep protocol and event parsing compatible with the backend before changing
  TUI presentation.
- Add command behavior under `cmd/`; keep reusable implementation under
  `internal/`.
- Update `README.md` and bundled skill material when commands, flags,
  configuration, or exit codes change.

## Verification

- Run `go test ./...`.
- Run `go build -o onyx-cli .`.
- Run `golangci-lint run ./...` when the linter is available.
- Exercise one non-interactive command with redirected stdout/stderr after
  changing output or exit behavior.

## Child DOX Index

No child guides are currently required; this file owns the complete CLI tree.
