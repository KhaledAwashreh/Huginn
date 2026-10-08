## Why

Users need a browser workspace for their configuration, and administrators need operational visibility. A shared frontend foundation avoids repeating session, API, navigation, and interaction behavior in every feature.

## What Changes

- Introduce Vue 3, TypeScript, Vite, Vue Router, PrimeVue, and TanStack Vue Query in a separate `frontend/` package.
- Establish a restrained application theme, responsive navigation, reusable form and table conventions, typed JSON transport, and consistent error states.
- Add a current-session bootstrap API so an existing HttpOnly session survives browser reload without storing credentials in JavaScript storage.
- Deliver login, logout, session-expiry handling, and an extension point for account-lifecycle and administrator pages.
- Document the five-module rollout and preserve FastAPI as the only application server.

## Capabilities

### New Capabilities

- `web-ui-foundation`: Browser shell, login/session behavior, shared interaction contracts, and same-origin frontend delivery.

### Modified Capabilities

None. Existing change artifacts remain intact; this adds a current-session read API without changing existing CRUD endpoints.

## Impact

Adds frontend tooling and narrow management session API extensions. Depends on the actual layered-management implementation in `feature/simple-matchmaking-service`, inspected at `ca2ddd9`, rather than replaying that restructure from the older primary checkout. Public signup, recovery, configuration editors, pipeline APIs, and pipeline screens are separate changes.

## Standards contract

Implementation follows the authoritative [foundation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) and the exact feature inventory in this change's design. This includes reproducible tooling/schema gates, existing Python conventions and explicit layer boundaries; browser work additionally targets WCAG 2.2 AA with automated and manual verification. These are planning refinements and do not authorize implementation or broaden product/ELT/security behavior.
