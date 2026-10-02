## Purpose

Defines owner-scoped discovery strategies that connect one ServiceOffering and one IdealClientProfile while permitting multiple simultaneous objectives.

## ADDED Requirements

### Requirement: Users manage multiple discovery strategies
The API SHALL provide create, paginated list, read, partial update, and delete operations under `/api/v1/discovery-strategies`. Each strategy SHALL have a UUID, authenticated User ownership, nonblank name, one offering reference, one ICP reference, an activity state, and creation and update timestamps.

#### Scenario: Strategy lifecycle
- **WHEN** an authenticated User creates, reads, updates, activates, deactivates, and deletes a valid strategy
- **THEN** each operation succeeds and list results reflect the committed state

### Requirement: New strategies are inactive
A newly created strategy SHALL default to inactive unless a valid explicit activity value is supplied, and activity SHALL be changeable through partial update.

#### Scenario: Default strategy state
- **WHEN** a strategy is created without `is_active`
- **THEN** the persisted strategy is inactive

### Requirement: Multiple active strategies are allowed
The system SHALL permit multiple active strategies for one User, including strategies that share the same offering or ICP.

#### Scenario: Shared active references
- **WHEN** a User activates two strategies that reference the same offering or ICP
- **THEN** both strategies remain active

### Requirement: Strategy references preserve ownership
Every referenced offering and ICP SHALL exist and belong to the authenticated User. The database and application SHALL reject missing references and cross-User reference injection, including direct or concurrent writes.

#### Scenario: Cross-User reference injection
- **WHEN** a User attempts to create or update a strategy with another User's offering or ICP
- **THEN** the API rejects the reference without revealing the other resource and persists no strategy change

### Requirement: Strategy lists are bounded and filterable
Strategy lists SHALL use deterministic ordering, nonnegative `offset`, a default `limit` of 50, a maximum `limit` of 100, and next-page metadata. The list SHALL support filtering by active state without exposing another User's strategies.

#### Scenario: List active strategies
- **WHEN** a User requests the active strategy filter
- **THEN** the response contains only that User's active strategies within the requested page

### Requirement: Strategy changes do not redefine Match identity
Creating, updating, activating, or deleting a strategy SHALL NOT create a second conceptual Match for the same User and Company. Future matching MAY record contributions from several strategies while retaining User-and-Company Match identity.

#### Scenario: Several strategies qualify one company
- **WHEN** multiple active strategies eventually qualify the same Company for one User
- **THEN** downstream matching retains one User-and-Company Match identity
