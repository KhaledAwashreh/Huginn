## Why

The existing owner provisioning CLI and login API do not support self-service registration or password recovery. Public users need these flows before they can configure discovery, with email verification required before first login.

## What Changes

- Add atomic public signup of Account, User, and an empty ProfessionalProfile, with no session issued before email verification.
- Add single-use, expiring verification and reset links, bounded resend/recovery requests, and durable transactional mail delivery through configurable SMTP.
- Keep username as the login identifier; use unique normalized email for verification resend and password recovery, with non-destructive conflict detection for existing data.
- Separate verified recovery email from editable profile contact email and preserve existing trusted owner accounts through an additive migration.
- Add create-account, check-email, verification, forgot-password, and reset-password screens to the shared frontend.

## Capabilities

### New Capabilities

- `public-account-lifecycle`: Public signup, required verification, recovery proof, lifecycle mail, and associated browser flows.

### Modified Capabilities

None in the current main spec tree. This explicitly supersedes the earlier phase's documented exclusion of public registration, while preserving existing authentication and owner-scoped CRUD contracts.

## Impact

Extends layered management domain, application, persistence, security, and API packages with additive SQL migrations and a dedicated mail-outbox worker. Depends on `web-ui-foundation` for browser delivery. No social login, billing, MFA, self-service role changes, or general account deletion is introduced.

## Standards contract

Implementation follows the authoritative [foundation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) and the exact feature inventory in this change's design. This includes reproducible tooling/schema gates, existing Python conventions and explicit layer boundaries; browser work additionally targets WCAG 2.2 AA with automated and manual verification. These are planning refinements and do not authorize implementation or broaden product/ELT/security behavior.
