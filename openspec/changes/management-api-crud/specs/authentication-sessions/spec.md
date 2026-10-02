## Purpose

Defines minimal password authentication, opaque server-side sessions, request protection, and authenticated User ownership for the management API.

## ADDED Requirements

### Requirement: Login authenticates without account disclosure
`POST /api/v1/sessions` SHALL accept username and password credentials, compare the password using the configured adaptive password verifier, and return the same generic authentication failure for an unknown username, invalid password, or disabled Account. Login attempts SHALL be subject to a bounded rate limit.

#### Scenario: Successful login
- **WHEN** valid credentials are supplied for an active Account
- **THEN** the system creates a session and returns an authenticated response without exposing credentials or hashes

#### Scenario: Rejected credentials
- **WHEN** the username is unknown, the password is invalid, or the Account is disabled
- **THEN** the system returns the same authentication error and creates no session

#### Scenario: Login throttling
- **WHEN** a caller exceeds the configured failed-login limit
- **THEN** further login attempts are temporarily rejected without revealing account existence

### Requirement: Sessions use opaque revocable tokens
A successful login SHALL generate an unpredictable opaque token, persist only its cryptographic digest with Account ownership, creation time, expiry time, and revocation state, and transport the raw token in an HttpOnly cookie. Production cookies MUST be Secure and use an explicitly configured SameSite policy.

#### Scenario: Stored session cannot authenticate by itself
- **WHEN** session persistence is inspected
- **THEN** it contains only the token digest and session metadata, not the raw browser token

#### Scenario: Expired or revoked session
- **WHEN** a request presents a token whose session is expired or revoked
- **THEN** the system rejects the request as unauthenticated

### Requirement: Unsafe cookie-authenticated requests resist CSRF
Every authenticated state-changing HTTP request SHALL require a CSRF value bound to the session in addition to the session cookie. Login and read-only requests MAY be exempt. Invalid or absent CSRF proof SHALL be rejected before application behavior runs.

#### Scenario: Missing CSRF proof
- **WHEN** an authenticated caller submits a state-changing request without valid CSRF proof
- **THEN** the system rejects the request and performs no write

### Requirement: Authentication resolves ownership server-side
Every protected request SHALL resolve Account and User from the valid session. Application behavior MUST derive ownership from that User and MUST ignore or reject caller-supplied ownership identifiers.

#### Scenario: Submitted ownership injection
- **WHEN** an authenticated request supplies another User's identifier
- **THEN** the operation does not change ownership or access the other User's data

### Requirement: Logout and credential changes revoke sessions
`DELETE /api/v1/sessions/current` SHALL revoke the current session. `PATCH /api/v1/me/password` SHALL require the current password, replace the stored hash, and revoke every existing session for the Account, including the session used for the change.

#### Scenario: Logout
- **WHEN** an authenticated caller logs out
- **THEN** the current session is revoked and subsequent use of its token fails

#### Scenario: Password change
- **WHEN** an authenticated caller supplies the correct current password and a valid new password
- **THEN** the password changes and every prior session is revoked

### Requirement: Authentication secrets are not observable
The API and application logs MUST NOT expose plaintext passwords, password hashes, raw session tokens, token digests, or CSRF secrets.

#### Scenario: Authentication failure logging
- **WHEN** authentication fails
- **THEN** logs contain safe operational context without credential or session secret values
