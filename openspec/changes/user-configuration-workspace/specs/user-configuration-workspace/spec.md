## Purpose

Let authenticated users manage the existing personal, professional, service-offering, ICP, and discovery-strategy definitions through coherent browser editors.

## ADDED Requirements

### Requirement: User-owned configuration navigation
The workspace SHALL expose Account, Professional profile, Service offerings, ICPs, and Discovery strategies as routable tabs. Every read/mutation SHALL use the authenticated user's existing ownership contracts; resource IDs or parent IDs SHALL NOT be treated as ownership proof.

#### Scenario: Another user's resource link
- **WHEN** a user opens or mutates an offering, ICP, or strategy belonging to another user
- **THEN** the server's generic 404 is shown safely and no other user's data enters the editor or cache.

### Requirement: Personal and password management
The Account tab SHALL edit first name, last name, contact email, phone number, country of residence, and nullable timezone using existing validation, and offer password change requiring current and new passwords. It SHALL not provide unimplemented username, role, status, recovery-email-replacement, or account-deletion controls. Password change SHALL follow existing all-session revocation and return the browser to login.

#### Scenario: Contact and timezone update
- **WHEN** a user changes contact data and explicitly clears timezone
- **THEN** the request sends only changed fields with timezone null and the saved server values become authoritative.

#### Scenario: Password change failure
- **WHEN** the server rejects a password change
- **THEN** the page shows a safe error without claiming success or persisting passwords in query state.

### Requirement: Structured professional profile editor
The Professional profile tab SHALL edit nullable headline and professional summary and structured skills, experience, and previous-project arrays. Skills SHALL contain only name; experience SHALL contain organization, role, optional summary/start_month/end_month, and is_current; previous projects SHALL contain name and description. Arrays SHALL preserve order and duplicates and use empty arrays to clear them. Experience dates SHALL use YYYY-MM and respect chronological/current-role rules.

#### Scenario: Clearing nullable and collection fields
- **WHEN** a user clears headline and removes all skills
- **THEN** the PATCH sends headline null and skills `[]`, not a null collection or omitted clear instruction.

#### Scenario: Current experience
- **WHEN** an experience row is marked current while an end month is supplied
- **THEN** validation prevents successful save and identifies that row without silently changing dates.

### Requirement: Service offering CRUD
The workspace SHALL list, create, edit, and delete user-owned service offerings with required nonblank name and description. Delete SHALL require an explicit confirmation and preserve the entry when the server returns a strategy-reference conflict.

#### Scenario: Referenced offering deletion
- **WHEN** an offering is referenced by a strategy and deletion returns 409
- **THEN** the offering remains visible and the interface directs the user to update or remove the strategy reference first.

### Requirement: Exact ICP editing contract
The workspace SHALL manage ICP name, industry-name arrays, company-size bands `0-10`, `11-100`, `101-1000`, `1001+`, country/region discriminated geographies, and company/industry/geography exclusions. Company exclusion SHALL accept the existing company UUID contract without inventing a company-search API. Region values SHALL remain representable without claiming current matchmaking supports them. Empty arrays and persisted ordering SHALL retain existing semantics.

#### Scenario: Region targeting
- **WHEN** a user adds a region geography
- **THEN** it is represented as `{kind:"region",value:...}` and the editor explains that the current matcher does not support region targeting rather than silently converting it to a country.

#### Scenario: Company exclusion
- **WHEN** a user supplies a company exclusion
- **THEN** the form submits a company UUID with the existing discriminated shape and shows safe server validation if unusable.

#### Scenario: Referenced ICP deletion
- **WHEN** an ICP is referenced by a strategy
- **THEN** its 409 deletion conflict preserves the ICP and explains how to resolve the reference.

### Requirement: Strategy links and activation
The workspace SHALL manage strategy name, exactly one user-owned service offering, exactly one user-owned ICP, and active/inactive state. New strategies SHALL default inactive in accordance with the existing API. Reference selectors SHALL provide all owned options through bounded paginated retrieval, not only the first page. Missing references and server conflicts SHALL not be silently substituted. Saving or activating a strategy SHALL not trigger matching or scraping.

#### Scenario: More than one page of references
- **WHEN** a user owns more than 100 offerings or ICPs
- **THEN** references beyond the first page remain selectable without exceeding server page limits.

#### Scenario: Activation
- **WHEN** a user saves is_active=true
- **THEN** the saved strategy state is shown and no pipeline/matchmaking invocation is issued.

### Requirement: Pagination and draft integrity
Collection pages SHALL follow existing `limit`, `offset`, `has_more` contracts with a maximum limit of 100, show bounded navigation, and retain valid page state after create/delete. Editing SHALL send changed fields only, preserve explicit null/empty values, and retain drafts after validation, reference conflict, or network failure. Unknown outcome SHALL require refetch/reconciliation rather than automatic mutation replay.

#### Scenario: Network loss after save
- **WHEN** a save response is lost and its commit outcome is unknown
- **THEN** the editor preserves its draft, explains the uncertainty, and offers a safe refresh before another explicit save.

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

### Requirement: Collected criterion selectors
The ICP editor SHALL present industry and country multi-select choices from authenticated read-only live Gold metadata and four company-size multiple toggles. It SHALL preserve exact stored values, order, duplicates and legacy unavailable entries until explicit removal. It SHALL offer grouped structured exclusions, collected-company name/domain search with bounded paging and selected-ID lookup, without free-form UUID entry or new unsupported regions. Counts SHALL describe individual collected coverage rather than combined match predictions. Empty required matcher categories SHALL be savable with clear incomplete-criteria feedback.

#### Scenario: Collected country spelling
- **WHEN** collected countries include USA and United States
- **THEN** the selector preserves each exact value and does not substitute an ISO country code.

#### Scenario: Legacy selections and unavailable company
- **WHEN** a draft contains a region, a value absent from collected options, or a removed company UUID
- **THEN** each remains in the draft with a clear retained/unsupported/unavailable label until explicitly removed, and background failures do not normalize or erase it.

### Requirement: Current professional experience control
The Experience editor SHALL allow only one newly selected current role, clear its actual end month upon selection and display Present in a disabled end-month field. Other current-role toggles SHALL remain disabled until the selected role is unchecked. Existing saved flags SHALL be preserved on load.

#### Scenario: Marking a role current
- **WHEN** a user marks a row current while an end month is present
- **THEN** its end month is explicitly cleared and other non-current rows cannot be marked current until it is unchecked.
