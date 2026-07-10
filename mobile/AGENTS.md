# AIPG Chat Mobile

## Purpose

Standalone Expo/React Native client. It has its own Bun dependency graph,
native prebuild lifecycle, API client, persisted query cache, and device state.

## Ownership

- `src/app/` - Expo Router routes and provider composition.
- `src/api/` - backend transport and authenticated requests.
- `src/query/` - TanStack Query setup and persistence.
- `src/state/` - MMKV-backed local state.
- `assets/` - app icons, splash art, and other bundled media.

## Local Contracts

- Store access tokens only through the platform's secure credential mechanism;
  never in AsyncStorage, logs, route parameters, or source-controlled env files.
- Mobile API behavior must match the backend's auth, tenant, streaming, and
  session contracts. Do not duplicate server authorization in client state.
- Treat generated `ios/` and `android/` projects as Expo prebuild output unless
  a native customization is intentionally documented.
- Preserve accessibility, safe-area, keyboard, offline, loading, and error
  states on both iOS and Android.

## Work Guidance

- Install and run commands from `mobile/` with Bun.
- Keep device persistence migrations backward compatible; users may upgrade
  over old local state.
- Update `README.md` and `GETTING_STARTED.md` when toolchain, ports, native
  prerequisites, or startup behavior changes.

## Verification

- Run `bun run typecheck`.
- Run `bun run lint` and `bun run format:check`.
- For native dependency or config changes, run `bun run prebuild` and launch at
  least one relevant simulator with `bun run run:ios` or `bun run run:android`.

## Child DOX Index

No child guides are currently required; this file owns the complete mobile
client.
