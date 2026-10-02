## Purpose

Defines owner-controlled provisioning and lifecycle behavior for the Account, User, and ProfessionalProfile aggregate that anchors every management capability.

## ADDED Requirements

### Requirement: Owner provisioning is atomic
The system SHALL provide an owner-only command that creates exactly one Account, one User linked to that Account, and one empty ProfessionalProfile linked to that User in one transaction. It MUST NOT expose public registration.

#### Scenario: Successful provisioning
- **WHEN** the owner supplies valid account credentials and all required User fields
- **THEN** the system creates the Account, User, and ProfessionalProfile together and returns their identifiers without returning the password hash

#### Scenario: Provisioning failure rolls back
- **WHEN** any validation, uniqueness, or persistence step fails
- **THEN** the system leaves none of the three aggregate records persisted

### Requirement: Provisioning validates identity input
The system SHALL require a trimmed nonblank username, a password satisfying the configured length bounds, trimmed nonblank first and last names, a valid email address, an E.164 phone number, and a nonblank country-of-residence label. The password SHALL be handled verbatim rather than trimmed or normalized. Timezone MAY be omitted, but when present it MUST be a valid IANA timezone. The initial ProfessionalProfile SHALL have null headline and professional summary values and empty skills, experience, and previous-project collections.

#### Scenario: Missing required identity input
- **WHEN** provisioning omits or supplies an invalid required field
- **THEN** the command fails with field-specific validation information before writing any aggregate record

### Requirement: Username identity is case-insensitive
The system SHALL preserve the accepted username spelling while enforcing uniqueness using its lowercase form, including under concurrent provisioning attempts.

#### Scenario: Case-variant duplicate
- **WHEN** an Account already has username `Alice` and provisioning requests `alice`
- **THEN** exactly one Account remains and the new request reports a username conflict

### Requirement: Passwords use established adaptive hashing
The system SHALL hash passwords with an established adaptive password-hashing implementation that creates a unique salt for every password. Plaintext passwords and password hashes MUST NOT appear in responses or logs.

#### Scenario: Provisioned password is protected
- **WHEN** provisioning succeeds
- **THEN** persistence contains an encoded salted password hash and contains no plaintext password

### Requirement: Account lifecycle is owner controlled
The owner command SHALL enable or disable an Account and SHALL reset its password without deleting the associated User or ProfessionalProfile. Disabling or resetting an Account SHALL revoke all of its active sessions.

#### Scenario: Account disablement
- **WHEN** the owner disables an active Account
- **THEN** the Account becomes disabled, its identity data remains, and all its sessions are revoked

#### Scenario: Owner password reset
- **WHEN** the owner resets an Account password
- **THEN** the new password replaces the prior hash and all existing sessions are revoked
