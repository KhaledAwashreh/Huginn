## Purpose

Allow public users to create verified accounts and recover credentials through safe, durable email-based lifecycle flows.

## ADDED Requirements

### Requirement: Atomic public signup
The system SHALL accept username, password, first name, last name, email, phone number, country of residence, and optional timezone using existing personal validation and an 8–16 character password containing a letter, at least one ASCII digit and at least one punctuation/symbol character. Country of residence SHALL be selected from a dropdown; its calling prefix SHALL be applied to the phone number. Browser and server SHALL enforce matching password, country and phone validation. Successful signup SHALL create exactly one Account, its User, an empty ProfessionalProfile, a pending recovery address, verification proof, and delivery intent atomically. Signup SHALL assign ordinary user privileges and SHALL NOT issue a session. Unknown fields, account status, role, and ownership overrides SHALL be rejected.

#### Scenario: New public user
- **WHEN** valid unused username, unused email and personal details are submitted
- **THEN** the server returns 202 with a check-email receipt, all identity rows are committed together, and login remains unavailable until verification.

#### Scenario: Provisioning rollback
- **WHEN** one identity or mail-intent write fails
- **THEN** no partial Account/User/Profile or unusable verification receipt is committed.

#### Scenario: Duplicate or privileged request
- **WHEN** a valid request names an existing username or normalized email
- **THEN** it returns the same safe 202 receipt without changing the existing account or its password.
- **WHEN** a request supplies role, account ID, status, or unexpected fields
- **THEN** it returns sanitized 422 validation and creates no privileged identity.

### Requirement: Verification before first login
New publicly registered accounts SHALL require email verification before login. Valid verification SHALL prove ownership of the originally requested email and make it the verified recovery destination without enabling a disabled account. Proof SHALL be purpose-bound, single-use, and expire. Unverified, disabled, nonexistent, and bad-password logins SHALL use the existing generic authentication rejection without issuing a session.

#### Scenario: Pending account cannot log in
- **WHEN** an unverified public registrant submits the correct password
- **THEN** login returns generic 401 and issues no session cookie.

#### Scenario: Verification completed
- **WHEN** an unexpired unused verification proof is submitted
- **THEN** verification completes atomically and the user can explicitly log in afterward if the Account is active.

#### Scenario: Invalid proof or disabled account
- **WHEN** a proof is invalid, expired, already consumed, or belongs to a disabled account
- **THEN** it cannot issue a session or reactivate the account; invalid proofs return safe validation guidance.

### Requirement: Bounded verification resend
The system SHALL accept verification resend by email with a generic 202 receipt independent of account existence or verification status. For an eligible pending account it SHALL enqueue a replacement link to its pending signup address and invalidate earlier verification proofs. Resend SHALL be throttled by normalized email and client IP.

#### Scenario: Resend pending verification
- **WHEN** an eligible pending user requests another link by pending email within allowed limits
- **THEN** a new delivery intent is committed, only the newest proof remains valid, and the receipt reveals no destination or account state.

#### Scenario: Delivery cooldown is non-enumerating
- **WHEN** repeated resend requests for pending, verified, or unknown email addresses are under the public normalized-key rate limits
- **THEN** all return the same 202 receipt, even when an internal cooldown suppresses actual mail for the pending account.

### Requirement: Verified-address password recovery
Forgot-password SHALL identify an account by its unique verified recovery email, return a generic 202 receipt, and enqueue reset mail only for an active eligible account with a verified recovery destination. Reset SHALL require an unexpired unused purpose-bound proof and a new password satisfying the same 8–16 character composition rule as signup, atomically replace the password, revoke every session, and invalidate outstanding reset proofs without automatically logging in.

#### Scenario: Existing recovery address
- **WHEN** an eligible user requests reset and completes its valid link
- **THEN** the password changes, every old session and reset proof becomes unusable, and explicit login is required.

#### Scenario: Unknown or ineligible email
- **WHEN** an email has no eligible active account with that verified recovery destination
- **THEN** forgot-password returns the same 202 receipt and exposes neither existence nor destination.

#### Scenario: Concurrent reset
- **WHEN** two requests attempt to consume the same reset proof
- **THEN** at most one password change commits and the other receives a safe invalid-proof response.

### Requirement: Contact email cannot redirect recovery
The existing editable `User.email` SHALL remain contact data. Changing it SHALL NOT change verified recovery identity or send reset links to the new value. Account views SHALL distinguish contact email from recovery email and explain that changing the latter is outside this initial slice.

#### Scenario: Contact email update
- **WHEN** a logged-in user updates their profile contact email
- **THEN** future password-recovery mail still targets the verified recovery address and the UI does not imply otherwise.

### Requirement: Durable safe lifecycle delivery
Lifecycle mail intents SHALL be durably committed with the relevant identity/proof transaction and dispatched outside HTTP requests with bounded retries. Responses SHALL not depend on SMTP latency. Mail links SHALL use configured trusted application origin, and secrets, passwords, proof values, addresses, and SMTP credentials SHALL not appear in public errors or operational logs. Verification/reset page rendering SHALL not consume proofs; consumption SHALL require explicit submission.

#### Scenario: Mail transport unavailable
- **WHEN** signup commits while SMTP is unavailable
- **THEN** its delivery intent remains recoverable for bounded retry and the account is not partially rolled back or silently verified.

#### Scenario: Link scanner visits
- **WHEN** an automated scanner loads a verification or reset link
- **THEN** it does not consume the proof or change credentials.

#### Scenario: Mail worker crash and obsolete proof
- **WHEN** a worker crashes after claiming an intent or its queued proof is invalidated before dispatch
- **THEN** abandoned claims can be retried within bounded budgets, stale workers cannot overwrite later claims, and a proof known obsolete is not sent.

### Requirement: Public browser lifecycle pages
The browser SHALL provide Create account, Check your email with resend, Verify email, Forgot password, and Reset password flows linked from login. Forms SHALL preserve non-secret drafts on errors, expose verification requirements, handle expired links and 429 safely, and remove proof data from navigable URLs after loading it into memory. Passwords and proof values SHALL not enter analytics, browser persistence, or query-cache payloads.

#### Scenario: Expired verification link
- **WHEN** a user submits an expired link
- **THEN** the page explains that a new link is needed and offers the email-based resend flow without a working-looking success state.

### Requirement: Preserve trusted existing accounts
The migration SHALL preserve existing identity rows, passwords, disabled/active state, and login ability of trusted owner-provisioned accounts. Existing contact addresses SHALL NOT silently become verified recovery destinations. Trusted accounts without a verified destination SHALL obtain recovery eligibility only through an explicit verified-email enrollment initiated by the authenticated account or trusted provisioning process.

#### Scenario: Existing disabled account
- **WHEN** the additive lifecycle migration is applied
- **THEN** its disabled state remains unchanged and no email-proof action reactivates it.

#### Scenario: Legacy owner recovery enrollment
- **WHEN** an authenticated trusted owner without a recovery address explicitly requests verification of their current contact email and completes the proof
- **THEN** that address becomes verified for recovery without changing the username or profile ownership.

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

### Requirement: Country and password form validation
Signup SHALL expose a labeled country dropdown, derive the visible phone calling prefix from that selection, and submit a validated E.164 phone number. Public signup and reset SHALL validate 8–16 Unicode code points, a Unicode letter, an ASCII digit and a Unicode punctuation/symbol character, rejecting controls. Whitespace SHALL NOT satisfy the special-character rule. Existing longer login credentials SHALL remain usable.

#### Scenario: Invalid account form
- **WHEN** country or phone input is invalid, or a new password violates length or composition
- **THEN** the browser explains the relevant field error and prevents submission, and direct API submissions receive sanitized 422.

#### Scenario: Changing selected country
- **WHEN** the user chooses a different country of residence
- **THEN** the displayed phone prefix changes and existing national digits are retained.

### Requirement: Unique account email
Contact email and pending-or-verified recovery destinations SHALL each be unique across accounts after trimming and case normalization. Signup SHALL reject reuse transactionally with the same generic receipt as duplicate username and SHALL NOT mutate the earlier account. Authenticated contact-email updates SHALL reject conflicting contact addresses and SHALL NOT redirect the verified recovery destination.

#### Scenario: Case-variant duplicate signup
- **WHEN** a different username signs up with a case variant of an existing contact or recovery address
- **THEN** no new account, proof or delivery intent is created and the response is a generic 202.

#### Scenario: Existing duplicate data
- **WHEN** the additive migration detects normalized duplicate email values
- **THEN** it aborts with operator guidance and preserves every pre-existing account, recovery identity and credential.

### Requirement: Actionable receipt forms
Forgot-password, verification resend and Check your email forms SHALL request and validate email, preserve its draft after errors and show action-specific guidance without revealing account eligibility. Signup and login SHALL retain their username fields.

#### Scenario: Invalid receipt input
- **WHEN** an email is missing or malformed
- **THEN** the form explains the email field error and prevents submission.
