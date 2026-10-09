## Why

Administrators need to trigger the existing collection pipeline and inspect progress for invocation X without inspecting database rows or server logs. A focused console exposes the new invocation contracts in the same application as user configuration.

## What Changes

- Add an administrator-only Data collection tab at the existing `/admin/pipeline` route with a Pull data action for the existing full HN/YC/EU-Startups pipeline.
- Add invocation detail with Source/Bronze, Silver, and Gold stage tabs, dependency skips, per-source detail, stage-count progress, counts, timestamps, a sanitized event history, and paginated companies written by that run's managed Gold company stage.
- Add paginated invocation history and bounded polling for active invocations with explicit stale/error states.
- Display observed progress without invented percentages, retain request identity across explicit uncertain retries, and keep accepted invocation identity available through history and deep links.

## Capabilities

### New Capabilities

- `admin-pipeline-console`: Role-gated browser trigger, invocation tracking, stage views, and history.

### Modified Capabilities

None. Administrator enforcement is owned by the server change, not browser navigation.

## Impact

Adds frontend pipeline feature modules. Depends on both `web-ui-foundation` and `pipeline-control-and-history`; `public-account-lifecycle` and configuration editors are independent. Does not add pipeline execution inside browser requests, expose raw logs and credentials, or add matcher execution to the collection flow.

## Standards contract

Implementation follows the authoritative [foundation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) and the exact feature inventory in this change's design. This includes reproducible tooling/schema gates, existing Python conventions and explicit layer boundaries; browser work additionally targets WCAG 2.2 AA with automated and manual verification. These are planning refinements and do not authorize implementation or broaden product/ELT/security behavior.
