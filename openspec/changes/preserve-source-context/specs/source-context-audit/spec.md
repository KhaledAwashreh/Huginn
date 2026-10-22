## Purpose

Compare proposed source-context output against persisted raw data and report
information retention, failure cases, and compatibility without changing records.

## ADDED Requirements

### Requirement: Read-only audit of stored input

The system SHALL provide an explicit audit mode that reads stored Bronze and
current downstream context without writes, collection, identity resolution network
calls, or model inference. Database reads SHALL have bounded timeouts. Output
SHALL identify code/parser version, input fingerprint, source counts, selection
method, and audit time without exposing credentials or private user data.

#### Scenario: Audit existing database
- **WHEN** an operator audits the configured persisted database
- **THEN** output contains proposed normalized context and comparisons while all database records remain unchanged

### Requirement: Reproducible selection and separate denominators

The audit SHALL support an all-record census and a deterministic source-stratified
sample selected before content-keyword filtering. It SHALL report eligible input,
excluded input, successful normalization, failed normalization, existing Silver,
resolved linkage, and Gold coverage separately. Signal counts SHALL NOT be
presented as unique-company counts or buying-opportunity counts.

#### Scenario: Unresolved HN records
- **WHEN** a valid HN comment lacks company identity
- **THEN** the audit counts its context result separately from its failure to reach Gold

### Requirement: Field retention and discrepancy report

The audit SHALL report per-source field coverage, header/body retention, separate
short/long descriptions, timestamp meanings, and discrepancies against current
staging and Gold. Every input SHALL receive an accounted outcome. Known removed
context SHALL be demonstrated with source-keyed before/after examples; increased
text length SHALL NOT be reported as increased buyer intent.

#### Scenario: Existing Gold lost header
- **WHEN** raw HN contains an employment restriction absent from Gold description
- **THEN** the report demonstrates its preservation in proposed output and labels it as retained employment context

#### Scenario: EU field absent downstream
- **WHEN** a listing country is present in stored HTML but absent in Gold
- **THEN** the report identifies recoverable source context without claiming that all ICP eligibility requirements now pass

### Requirement: Honest failure and reproducibility handling

Invalid selection arguments SHALL fail before data access. Unavailable databases,
malformed records, or incompatible schemas SHALL produce safe failures rather
than empty-success reports. The system SHALL allow comparison of two audit runs
only with their input fingerprints and versions visible, so changed source data
cannot be confused with parser improvements.

#### Scenario: Changed input between audits
- **WHEN** a second audit reads different raw content
- **THEN** its fingerprint differs and the comparison identifies the input change rather than attributing all differences to implementation

### Requirement: Evidence artifacts remain local

Detailed source text SHALL be an explicit local artifact, excluded from version
control by default. Routine summaries SHALL contain aggregate results and stable
source identifiers rather than credentials or personal contact text. Curated test
fixtures SHALL retain necessary semantics while removing irrelevant contact data.

#### Scenario: Report generation
- **WHEN** audit produces a summary and detailed comparison file
- **THEN** the summary is safe to review and the detailed local file is not automatically committed or transmitted externally
