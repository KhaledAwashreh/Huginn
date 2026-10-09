## Why

Authenticated users can define discovery strategies, but have no browser view of the companies already recorded for them. This change gives each user a bounded, read-only Matches workspace that presents their own match records alongside clearly labeled current company and signal context.

## What Changes

- Add authenticated, owner-scoped read APIs for a paginated match list, one match detail, that match's paginated current company signals, and a read-only overview for meaningful empty states.
- Add a Matches navigation entry and `/matches` list and `/matches/:id` detail routes with status filtering, newest-match ordering, accessible loading/empty/error states, and safe external company links.
- Display existing match status, timestamps, and notes with current Gold company fields and current company signals. Label company and signal fields as current context; do not imply they explain why a match originally qualified.
- Keep all endpoints read-only. Do not add matching execution, user-controlled company lookup, score or rationale generation, CRM actions, or match status, note, activity, or communication writes.
- Derive overview states only from authenticated user's active strategies and durable matching-run records. Depend on `admin-matchmaking-execution`'s owner-readable run projection; incomplete or unavailable evaluation history must not be shown as a definitive zero-result evaluation.

## Capabilities

### New Capabilities

- `user-matches-view`: Authenticated users browse their own existing matches and read current company and signal context.

### Modified Capabilities

None.

## Impact

Adds read-only management API contracts and a Matches feature to the authenticated Vue application. Reads `operational.match`, `gold.company`, and `gold.company_signal`; the empty-state overview also reads the user's active strategies and the owner-scoped durable matching-run projection introduced by `admin-matchmaking-execution`. Depends on `user-configuration-workspace` for the strategy model and `web-ui-foundation` for authentication, navigation, query-cache isolation, generated API types, and shared UI. No schema or data migration is required by this change.
