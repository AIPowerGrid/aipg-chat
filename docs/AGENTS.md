# docs - chat and Craft documentation

## Purpose

Architecture, product, implementation-plan, deployment, security, and testing
notes for the AIPG Onyx fork, especially the Craft/build system.

## Ownership

- `craft/` - Craft product, backend, sandbox, streaming, Kubernetes/Docker,
  security, issue, and test plans.
- `dev/` - local development and environment runbooks.

## Local Contracts

- Distinguish accepted/current behavior from proposals, migration plans, issue
  notes, and legacy designs in the title or opening status block.
- Commands, paths, endpoints, flags, and environment variables must exist in the
  current tree before a doc calls them runnable.
- Security docs describe the enforced boundary, not the intended one. Auth,
  ownership, sandbox network, egress/IMDS, secrets, quotas, and cleanup claims
  require code/test evidence.
- Do not publish production credentials, internal hosts, customer data, or
  exploit details that have not been remediated.
- Remove or repair broken cross-links when moving/replacing a plan.

## Work Guidance

- Update the owning code comments/README and relevant plan when a durable Craft
  protocol or deployment contract changes.
- Archive superseded plans under an explicit legacy location rather than leaving
  two apparently current sources of truth.

## Verification

- `git diff --check`
- Run a local Markdown-link check for touched docs.
- Execute or dry-run operator commands where safe.

## Child DOX Index

- None - `craft/` and `dev/` inherit this guide.
