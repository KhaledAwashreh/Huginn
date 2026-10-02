## Purpose

Defines authenticated self-service access to personal contact data and structured professional profile information without exposing arbitrary User administration.

## ADDED Requirements

### Requirement: Current User is readable and partially updateable
`GET /api/v1/me` SHALL return the authenticated User's personal and contact fields. `PATCH /api/v1/me` SHALL update only supplied mutable fields, preserve omitted fields, and reject changes to identifiers, Account linkage, ownership, and timestamps.

#### Scenario: Read current User
- **WHEN** an authenticated User requests `/api/v1/me`
- **THEN** the API returns only that User's public management fields and excludes Account credentials

#### Scenario: Partial User update
- **WHEN** an authenticated User submits valid changes to a subset of mutable fields
- **THEN** the system updates those fields, preserves omitted fields, and advances `updated_at`

### Requirement: Required User fields remain valid
First name, last name, email, phone number, and country of residence SHALL remain present and valid after every update. Timezone MAY be null and MUST be a valid IANA timezone when present.

#### Scenario: Required field is cleared
- **WHEN** an update attempts to clear or invalidate a required User field
- **THEN** the API returns a validation error and leaves the User unchanged

### Requirement: ProfessionalProfile is readable and partially updateable
`GET /api/v1/me/professional-profile` SHALL return the authenticated User's profile. `PATCH /api/v1/me/professional-profile` SHALL support nullable headline and professional summary plus complete replacement of any supplied collection while preserving omitted fields.

#### Scenario: Blank profile read
- **WHEN** a newly provisioned User reads the profile
- **THEN** headline and professional summary are null and all three collections are empty arrays

#### Scenario: Explicit profile clearing
- **WHEN** a patch supplies null for a nullable text field or `[]` for a collection
- **THEN** the field or collection is cleared and omitted fields remain unchanged

### Requirement: Professional collections use the established shapes
Skills SHALL contain only a nonblank `name`. Experience items SHALL require nonblank `organization` and `role`, MAY contain nonblank `summary`, optional `start_month` and `end_month`, and an `is_current` flag; end month MUST NOT precede start month and current experience MUST NOT have an end month. Previous projects SHALL require nonblank `name` and `description`. Unknown fields and coercion SHALL be rejected.

#### Scenario: Invalid nested profile item
- **WHEN** a supplied collection item has an unknown field, malformed month, blank required value, reversed month range, or current experience with an end month
- **THEN** the entire profile update fails atomically and the prior profile remains unchanged

### Requirement: Profile writes use replacement and last-write-wins semantics
Supplying a collection SHALL replace that whole ordered collection, including duplicates; item-level patching is not supported. Concurrent valid writes SHALL use last-write-wins behavior for the MVP, and `updated_at` SHALL identify the latest committed write.

#### Scenario: Collection replacement
- **WHEN** a patch supplies a new skills collection
- **THEN** the stored skills collection exactly matches the supplied order and the other profile fields are preserved

### Requirement: Self-service endpoints are owner isolated
The self-service API SHALL expose only the User resolved from the session and SHALL provide no route for selecting another User identifier.

#### Scenario: Another User exists
- **WHEN** two Users are provisioned and either calls a self-service endpoint
- **THEN** each caller can read and modify only their own User and ProfessionalProfile
