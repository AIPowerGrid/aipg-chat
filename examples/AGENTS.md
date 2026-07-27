# AIPG Chat Examples

## Purpose

Small, non-production examples for Chat APIs and widget embedding. Examples are
discoverable copy-paste surfaces, so their security and endpoint assumptions
must be at least as strict as production docs.

## Ownership

- `assistants-api/` - Python API usage examples.
- `widget/` - standalone widget embedding example.

## Local Contracts

- Never commit credentials. Examples read environment variables and use
  placeholders that cannot be mistaken for valid secrets.
- Clearly label Onyx-upstream versus AIPG deployment URLs and authentication.
- Browser examples may use only client-visible, revocable, origin/rate-limited
  widget credentials; never an admin, session, billing, or general Grid key.
- Do not present experimental endpoints as stable production contracts.

## Work Guidance

- Keep examples minimal, runnable, and linked to the owning current docs.
- Update examples in the same change as the public API they demonstrate.

## Verification

- Install/run each changed example from a clean directory with synthetic or
  mocked credentials.
- Scan generated bundles for secrets and local absolute paths.

## Child DOX Index

No child guides are currently required; this file owns `examples/`.
