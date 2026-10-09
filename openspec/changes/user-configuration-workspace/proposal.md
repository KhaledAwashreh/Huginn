## Why

Owner-scoped JSON CRUD already exists for personal and professional details, offerings, ICPs, and strategies. Users need coherent editors for those definitions instead of constructing API requests manually.

## What Changes

- Add Account, Professional profile, Service offerings, ICPs, and Discovery strategies navigation tabs and editors.
- Use existing typed request/response contracts, ownership rules, pagination, PATCH semantics, and deletion-reference conflicts.
- Keep one strategy linked to one user-owned offering and one user-owned ICP, with explicit active/inactive control.
- Preserve form drafts on errors, provide save/cancel behavior, and handle empty, loading, validation, and conflict states.

## Capabilities

### New Capabilities

- `user-configuration-workspace`: Browser editors for implemented user-owned configuration definitions.

### Modified Capabilities

None. Existing management APIs and matching rules remain unchanged.

## Impact

Adds frontend feature modules against `/api/v1/me`, `/me/professional-profile`, `/offerings`, `/ideal-client-profiles`, and `/discovery-strategies`. Depends on `web-ui-foundation`; existing provisioned accounts can use this before public signup ships. No Match workflow, scores, feedback, CRM, buyer-persona editor, or engagement-preference editor is implied by WIP entities.

## Standards contract

Implementation follows the authoritative [foundation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) and the exact feature inventory in this change's design. This includes reproducible tooling/schema gates, existing Python conventions and explicit layer boundaries; browser work additionally targets WCAG 2.2 AA with automated and manual verification. These are planning refinements and do not authorize implementation or broaden product/ELT/security behavior.
