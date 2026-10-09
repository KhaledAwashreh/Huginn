## Why

Users can configure offerings, ICPs, and active strategies, but matchmaking currently requires an operator CLI and has no durable browser-visible execution history. Administrators need to run the existing matcher for a selected user or all eligible users and inspect the outcome without running work inside an HTTP request.

## What Changes

- Add administrator-only Matchmaking pages with user search, single-user/all-eligible targeting, an explicit signal window, manual trigger, progress, and paginated run/results history.
- Add durable PostgreSQL queuing and an immutable target-user snapshot; execute the existing creation-only matchmaking service, retaining its criteria, per-user transaction/retry rules, deduplication, and status/notes preservation.
- Track acknowledged per-user results, skipped strategies, failures, and uncertain outcomes; show processed-user progress rather than guessed company-scan percentages.
- Reuse the pipeline change's authoritative roles and extend its shared execution guard so collection and matching execution cannot overlap through supported full CLI/managed entrypoints.
- Provide owner-scoped run-result projections for the separate read-only `user-matches-view` change. No administrator role is required to read one's own matches.

## Capabilities

### New Capabilities

- `admin-matchmaking-execution`: Authorized matchmaking trigger, durable queue/target identity, execution progress/results, and administrator browser controls.

### Modified Capabilities

None in the main spec tree. This depends on the planned `pipeline-control-and-history` role/guard contracts and complements `admin-pipeline-console`; matching remains separate from collection, not an ELT stage.

## Impact

Add a sibling `huginn.matchmaking_control` boundary, additive ops tables, narrow matcher bootstrap/CLI wiring, management app composition, and `frontend/src/features/matchmaking/`. Reuse the existing database/client, sessions, CSRF, foundation components/tooling, pipeline supervision, and existing `huginn.matchmaking` application service. No additional infrastructure, evaluator/scoring changes, scheduler, automatic post-collection matching, status/notes editor, digest, outreach, or new scraper.

Implementation requires the actual merged successors of foundation, lifecycle, user configuration, and the existing matcher, followed by `pipeline-control-and-history`. The admin collection UI is independently shippable. This proposal authorizes planning only; implementation, real-data migrations/execution, and publication require later instructions.
