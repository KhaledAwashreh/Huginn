## Purpose

Defines authenticated lifecycle management for the reusable services a User offers to prospective clients and references from discovery strategies.

## ADDED Requirements

### Requirement: Users manage multiple offerings
The API SHALL provide create, paginated list, read, partial update, and delete operations under `/api/v1/offerings`. Each offering SHALL have a UUID, authenticated User ownership, nonblank name and description, and creation and update timestamps.

#### Scenario: Offering lifecycle
- **WHEN** an authenticated User creates, reads, updates, and deletes an unreferenced valid offering
- **THEN** each operation succeeds and list results reflect the committed state

#### Scenario: Invalid offering
- **WHEN** an offering create or update supplies a blank name or description or an unknown field
- **THEN** the API returns a validation error and performs no write

### Requirement: Offering ownership is immutable and isolated
The system SHALL derive `user_id` from authentication, SHALL NOT accept ownership assignment or transfer, and SHALL prevent cross-User reads and writes. A resource belonging to another User SHALL appear not found.

#### Scenario: Cross-User offering access
- **WHEN** one User addresses another User's offering identifier
- **THEN** the API returns not found and does not reveal or change the offering

### Requirement: Offering lists use bounded pagination
Offering lists SHALL accept nonnegative `offset` and a bounded `limit`, defaulting to 50 and not exceeding 100, and SHALL return deterministic ordering with enough metadata to request the next page.

#### Scenario: Oversized page
- **WHEN** a caller requests a limit greater than 100
- **THEN** the API rejects the request as invalid rather than returning an unbounded result

### Requirement: Referenced offerings cannot be deleted
An offering referenced by any discovery strategy SHALL remain protected by database referential integrity and the API SHALL report a conflict instead of deleting it.

#### Scenario: Delete referenced offering
- **WHEN** an authenticated User deletes an offering referenced by one of their strategies
- **THEN** the API returns a conflict and preserves both resources
