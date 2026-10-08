## Purpose

Provide a consistent browser application shell and safe JSON session transport for user configuration and administrator operations.

## ADDED Requirements

### Requirement: Authenticated application shell
The browser SHALL provide a login page and a responsive authenticated shell with routable feature tabs. Unauthenticated access to protected pages SHALL redirect to login with only a validated local return path. Navigation SHALL expose implemented features only and SHALL support browser reload and direct links.

#### Scenario: Direct protected link
- **WHEN** an unauthenticated user opens a configuration route
- **THEN** login is shown and a successful login returns to that local route without accepting external redirect destinations.

#### Scenario: Responsive navigation
- **WHEN** a user operates the shell at a narrow viewport or with a keyboard
- **THEN** every available tab and logout action remains reachable with visible focus and an identifiable selected state.

### Requirement: Reloadable cookie session
The server SHALL expose `GET /api/v1/sessions/current` returning `account_id`, `user_id`, `csrf_token`, and `expires_at` for a valid active session, without exposing the opaque session credential. Once administrator roles ship, this response SHALL also include the current server-authoritative `role`. Responses SHALL be private and non-cacheable. The browser SHALL restore session context on reload and keep the CSRF proof only in memory.

#### Scenario: Reload with existing session
- **WHEN** a user reloads a protected route with a valid HttpOnly session cookie
- **THEN** the shell restores authentication and can submit a subsequent CSRF-protected mutation without another login.

#### Scenario: Invalid session bootstrap
- **WHEN** the cookie is missing, expired, revoked, or belongs to a disabled account
- **THEN** bootstrap returns the existing generic 401 contract and no user or credential data.

#### Scenario: Multiple browser tabs
- **WHEN** two tabs bootstrap the same valid session
- **THEN** their returned CSRF proofs remain compatible with that session and one bootstrap does not invalidate the other tab's proof.

### Requirement: Login and logout lifecycle
The browser SHALL use existing username/password login and cookie transport, show safe authentication/rate-limit errors, prevent duplicate submission, and clear private cached data on logout, password change, account switch, or session expiry. Password change SHALL end the current browser session in accordance with the server's existing revocation behavior.

#### Scenario: Session ends during editing
- **WHEN** an API request returns 401 while a form is open
- **THEN** authenticated cached data and session proof are cleared, no mutation is automatically retried, and login is required before continuing.

#### Scenario: Logout
- **WHEN** logout succeeds or the server reports that the session is already invalid
- **THEN** private cached responses and in-memory session state are removed and login is shown.

### Requirement: Typed JSON and error handling
The browser SHALL consume documented JSON contracts with cookie credentials and session-bound `X-CSRF-Token` on authenticated unsafe requests. It SHALL handle 204 without parsing JSON, sanitized native 422 `detail` validation arrays, and existing `error` envelopes. A 403 SHALL remain an authorization/CSRF error, not be silently treated as session expiry; unsafe requests SHALL not be automatically replayed.

#### Scenario: Field validation
- **WHEN** a server returns native 422 details identifying a nested field
- **THEN** the corresponding editor shows safe field guidance and preserves submitted values.

#### Scenario: Forbidden mutation
- **WHEN** a mutation returns 403
- **THEN** the interface reports the failure, retains the draft, and does not silently retry or clear a valid session as though it received 401.

### Requirement: Shared usable interaction states
Forms and lists SHALL use consistent visible labels, primary actions, loading, empty, error, success, and unsaved-change behavior. Form drafts SHALL remain separate from fetched server data and background refresh SHALL not overwrite unsaved edits. Status information SHALL include text, and layouts SHALL support keyboard access, reduced motion, readable contrast, and long content.

#### Scenario: Refetch with dirty form
- **WHEN** a background query completes while the user has unsaved changes
- **THEN** the current draft remains intact and saving/canceling remains explicit.

### Requirement: Same-origin application delivery
Production SHALL serve the browser application and its JSON API under one origin, preserve API/docs/health routes, and support protected-page deep links. Session credentials SHALL not be placed in browser storage or exposed through generated API types.

#### Scenario: Frontend deep link
- **WHEN** a browser requests an application route directly
- **THEN** it receives the application shell while missing API paths continue to return API errors instead of HTML.

### Requirement: Shared standards and explicit placement
Implementation SHALL comply with the authoritative [foundation standards](../../../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) and this change's exact design inventory. New application ports SHALL use `application/protocols`; existing persistence conventions SHALL be preserved. Domain SHALL not import application/read-model/HTTP/persistence types. New Python value types SHALL be frozen dataclasses and new application use cases SHALL expose `execute(Request) -> Response`. Pyright adoption remains deferred. Schema changes SHALL regenerate the shared offline OpenAPI/TypeScript artifacts and pass the drift gate.

#### Scenario: Review implementation placement
- **WHEN** this change adds a service, type, query projection, repository, row model, or browser feature
- **THEN** its named file and dependency direction follow the exact design inventory and shared conventions without duplicate session/database/tooling definitions.

### Requirement: Reproducible browser verification
Browser implementation SHALL use the foundation's pinned Node/npm lockfile, strict SFC/tooling type checks, ESLint/Prettier, Vitest/Vue Test Utils, Playwright/axe, and named CI/hook gates. User-facing pages SHALL target WCAG 2.2 AA with manual keyboard/focus/reflow/contrast checks supplementing automated scans. API-only startup SHALL remain independent of Node and frontend build artifacts.

#### Scenario: Required browser gate
- **WHEN** a browser feature or API schema changes
- **THEN** its applicable foundation checks fail on type/lint/format/schema/interaction errors and missing prerequisites are reported rather than treated as a passing skip.
