# AIPG Chat Developer Tools

## Purpose

Repository-local developer and operator utilities. The primary tool is `ods`,
a Go binary packaged in the `onyx-devtools` Python wheel.

## Ownership

- `ods/cmd/` - CLI commands.
- `ods/internal/` - Docker, Kubernetes, database, migration, OpenAPI, CI,
  screenshot, and repository helpers.
- `ods/hatch_build.py` and `ods/pyproject.toml` - wheel packaging of the Go
  binary.

## Local Contracts

- Tooling that touches containers, databases, clusters, AWS, or GitHub must
  make its target explicit and default to the least destructive operation.
- Never print credentials or copy secrets into generated artifacts. Redact
  command output used in diagnostics.
- Destructive or production-affecting commands require an explicit target and
  confirmation; do not infer production from ambient credentials.
- Keep the wheel's embedded binary version and source version synchronized.

## Work Guidance

- Put reusable behavior under `ods/internal/` and keep command wiring thin.
- Preserve cross-platform path and subprocess behavior where supported.
- Update `ods/README.md`, command help, and autocomplete when flags or commands
  change.

## Verification

- From `tools/ods`, run `go test ./...` and `go build .`.
- Exercise the affected command's `--help` and a non-destructive path.
- Build the Python wheel when changing packaging or version integration.

## Child DOX Index

No child guides are currently required; this file owns `ods/`.
