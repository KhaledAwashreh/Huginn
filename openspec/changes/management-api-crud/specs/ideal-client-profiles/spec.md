## Purpose

Defines owner-scoped IdealClientProfile lifecycle and the deliberately broad flat targeting semantics used by the management MVP and future matching.

## ADDED Requirements

### Requirement: Users manage multiple IdealClientProfiles
The API SHALL provide create, paginated list, read, partial update, and delete operations under `/api/v1/ideal-client-profiles`. Each ICP SHALL have a UUID, authenticated User ownership, nonblank name, industries, company sizes, geographies, exclusions, and creation and update timestamps.

#### Scenario: ICP lifecycle
- **WHEN** an authenticated User creates, reads, updates, and deletes an unreferenced valid ICP
- **THEN** each operation succeeds and list results reflect the committed state

### Requirement: ICP criteria use typed atomic collections
Industries SHALL be nonblank labels. Company sizes SHALL use the supported company-scale bands. Geographies SHALL distinguish country and region labels. Exclusions SHALL distinguish company, industry, and geography exclusions and carry the identifier or label appropriate to their type. Unknown item fields, unsupported types, invalid identifiers, and malformed values SHALL reject the entire write.

#### Scenario: Invalid criterion in a collection
- **WHEN** any criterion or exclusion item is malformed
- **THEN** the API returns field-specific validation information and persists none of the requested ICP changes

### Requirement: Positive criteria use flat broad combinations
Industries, company sizes, and geographies SHALL be independent positive dimensions. Values within one dimension SHALL combine with OR, and the three dimensions SHALL combine with AND. Every selected value in one dimension MAY combine with every selected value in the other dimensions; the system SHALL NOT require or materialize correlated Cartesian tuples.

#### Scenario: Broad multi-value match
- **WHEN** an ICP selects SaaS and Fintech, Small and Large, and Germany and Netherlands
- **THEN** any company satisfying one selected industry, one selected size, and one selected geography satisfies the positive criteria regardless of which selected values form that combination

### Requirement: Empty positive dimensions yield no matches
If industries, company sizes, or geographies is empty, downstream ICP evaluation SHALL short-circuit to an empty result without querying candidate companies. CRUD SHALL allow empty positive collections so an ICP can be saved progressively.

#### Scenario: Incomplete ICP evaluation
- **WHEN** any positive collection is empty
- **THEN** evaluation returns no matches before candidate selection

### Requirement: Exclusions are global hard vetoes
Any matching exclusion SHALL reject a company after positive criteria are satisfied. An empty exclusion list SHALL add no veto. Preference weighting and correlated segment-specific exclusions are outside the MVP.

#### Scenario: Positive match is excluded
- **WHEN** a company satisfies all positive dimensions and also matches any exclusion
- **THEN** the company is excluded from the result

### Requirement: ICP collection updates replace supplied collections
A supplied ICP collection SHALL replace that entire ordered collection; omitted fields SHALL be preserved and explicit `[]` SHALL clear a collection. Valid writes use last-write-wins semantics and advance `updated_at`.

#### Scenario: Clear one criterion collection
- **WHEN** a patch supplies `[]` for geographies and omits industries
- **THEN** geographies becomes empty, industries remains unchanged, and evaluation subsequently yields no matches

### Requirement: ICP ownership and deletion are protected
The system SHALL derive ownership from authentication, make another User's ICP appear not found, and report a conflict when deleting an ICP referenced by a discovery strategy.

#### Scenario: Delete referenced ICP
- **WHEN** a User deletes an ICP referenced by their strategy
- **THEN** the API returns a conflict and preserves both resources

### Requirement: ICP lists use bounded pagination
ICP lists SHALL use deterministic ordering with nonnegative `offset`, a default `limit` of 50, a maximum `limit` of 100, and next-page metadata.

#### Scenario: Paginated ICP list
- **WHEN** a User requests a valid bounded page
- **THEN** the response contains only that User's ICPs in deterministic order and indicates whether another page exists
