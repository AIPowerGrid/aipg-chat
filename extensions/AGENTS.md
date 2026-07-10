# AIPG Chat Browser Extensions

## Purpose

Browser extension surfaces for AIPG Chat. The current Chrome Manifest V3
extension provides a side panel, popup, new-tab page, omnibox integration, and
page-selection helper.

## Ownership

- `chrome/manifest.json` - permissions, host access, entrypoints, and commands.
- `chrome/service_worker.js` - privileged background behavior.
- `chrome/src/pages/` - popup, options, side-panel, and new-tab pages.
- `chrome/src/utils/` - content scripts injected into visited pages.

## Local Contracts

- Treat extension permissions as a security and privacy contract. Justify any
  addition to `permissions`, `host_permissions`, content-script matches, or
  web-accessible resources.
- Page content is untrusted. Keep privileged actions in the service worker,
  validate messages and URLs, and never inject unsanitized HTML.
- Never expose session cookies, bearer tokens, selected private text, or page
  contents to logs, analytics, arbitrary origins, or extension storage without
  an explicit reviewed purpose.
- Preserve Manifest V3 CSP and avoid remote executable code.

## Work Guidance

- Keep browser-specific behavior under its browser directory.
- Update the browser README and store disclosure whenever permissions,
  collected data, keyboard commands, or user-visible behavior changes.
- Prefer narrow host matches over `<all_urls>` when the feature permits it.

## Verification

- Load `chrome/` as an unpacked extension and exercise the popup, side panel,
  new-tab override, options page, and service-worker restart.
- Review the final manifest diff and Chrome extension error console.
- Verify content scripts do not break unrelated pages or transmit page data.

## Child DOX Index

No child guide is currently required; this file owns `chrome/` and future
browser-specific extension directories.
