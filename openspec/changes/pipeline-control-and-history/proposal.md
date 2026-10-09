## Why

The pipeline currently runs through operator CLIs and records independent source/stage job rows. An administrator needs a safe manual trigger and a durable invocation identity that groups all work and its history.

## What Changes

- Add server-enforced user/admin roles with trusted operator assignment; public signup and existing accounts default to user.
- Add manual invocation creation, durable queuing, a dedicated worker process, and authenticated administrator history/detail/event APIs.
- Persist explicit invocation-to-stage/source-job relationships, known stage plans, lifecycle events, actual counters, and sanitized errors.
- Persist invocation-scoped attribution for companies successfully written by the managed Gold company stage, and expose a bounded administrator results page/API.
- Preserve current HN/YC/EU-Startups pipeline order and dependency-aware skips; OpenCorporates remains outside the full pipeline.
- Bound pipeline execution through the shared execution guard and make crash/commit-uncertainty behavior visible without silently replaying work; a separate administrator matchmaking operation may later use the same guard without becoming a pipeline stage.

## Capabilities

### New Capabilities

- `pipeline-control-and-history`: Administrator authorization, durable invocation execution, per-stage/source tracking, and history APIs.

### Modified Capabilities

None in the current main spec tree. This deliberately introduces role-based access that the earlier phase excluded, without rewriting earlier change artifacts or ELT business rules.

## Impact

Adds a sibling `huginn.pipeline_control` application boundary, narrow management authorization extensions, ops migrations, and explicit ELT tracking hooks. Depends on the existing layered management and ELT implementations. Server runtime and backend-only tests require no frontend runtime or Node; shared foundation planning standards apply, and once foundation tooling exists, API schema changes regenerate its owned OpenAPI/TypeScript artifacts and pass the offline drift gate. No scheduler, arbitrary job execution, source editing, stage-only reruns, cancellation, automatic replay, matcher execution inside the pipeline, or new scraper is included. The separate `admin-matchmaking-execution` change may extend the shared guard additively for mutual exclusion; this change continues to claim it only for pipeline execution.

## Standards contract

Implementation follows the authoritative [foundation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) and the exact feature inventory in this change's design. This includes reproducible tooling/schema gates, existing Python conventions and explicit layer boundaries; browser work additionally targets WCAG 2.2 AA with automated and manual verification. These are planning refinements and do not authorize implementation or broaden product/ELT/security behavior.
