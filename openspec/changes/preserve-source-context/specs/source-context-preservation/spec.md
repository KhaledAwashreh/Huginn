## Purpose

Preserve complete, source-attributed context from already collected startup
records so downstream evaluation can inspect meaning without changing eligibility.

## ADDED Requirements

### Requirement: Immutable source context independent of company identity

The system SHALL preserve each successfully normalized source record with its
source, stable ID, payload digest, parser version, normalized text, source fields,
and source URL. Company resolution SHALL NOT be required. Reprocessing identical
input with the same parser version SHALL reuse the same snapshot; changed input
or parser version SHALL create a distinct snapshot without altering prior text.

#### Scenario: Unresolved company
- **WHEN** an HN comment has usable text but no resolved company
- **THEN** context is preserved by source and stable ID without creating or linking a confirmed company

#### Scenario: Repeat and changed input
- **WHEN** identical input is captured twice and then captured after its content changes
- **THEN** the first two captures reference the same snapshot and the third references a new snapshot while the original remains readable

### Requirement: Preserve HN header and body

The system SHALL preserve the complete normalized text of a nonempty HN comment,
including the header, with recoverable header/body boundaries. It SHALL retain
role, engagement, location, compensation, and link text present in that content
without inferring company geography or buyer intent. Roots and deleted/dead or
empty records SHALL receive explicit exclusion outcomes rather than opportunity
snapshots. Original collected payloads SHALL remain unchanged.

#### Scenario: Full-time restriction in header
- **WHEN** the header contains a full-time role and the body describes technical work
- **THEN** the full-time restriction is present in the preserved context and can be traced to the header

#### Scenario: No paragraph separator
- **WHEN** a comment has one text block with no separable header and body
- **THEN** its entire normalized text remains available and the unknown separation is explicit rather than dropping the block

#### Scenario: Root or unavailable comment
- **WHEN** input is a story root or a deleted, dead, or textless comment
- **THEN** capture reports the applicable exclusion reason and creates no new opportunity context for that input

### Requirement: Preserve EU listing-specific fields

The system SHALL preserve EU short and long business descriptions separately,
along with source country/category, place, tags, website, founding, funding, and
status where supplied. Missing optional fields SHALL remain missing. Page
navigation, scripts, and footer content SHALL NOT be used as listing evidence.
Source category/place/tags SHALL NOT be silently mapped to canonical geography
or sectors in this change.

#### Scenario: Longer description and source geography
- **WHEN** a listing provides short and long descriptions, country, place, and tags
- **THEN** both descriptions and the source attributes remain separately available even if current Gold lacks them

#### Scenario: Missing listing structure
- **WHEN** a stored page contains navigation but no trustworthy listing fields
- **THEN** the record is reported as unparseable and navigation is not emitted as business context

### Requirement: Preserve YC context and source states

The system SHALL preserve separate one-line and long descriptions, tags, regions,
industries, industry/subindustry labels where supplied, exact team size, location
text, batch, source status, launch timestamp, and hiring flag. False, unknown,
zero, and absent values SHALL remain distinguishable. Records disqualified from
current descriptive staging SHALL still yield a source status observation when
the payload is valid. Capturing that observation SHALL NOT activate the listing.

#### Scenario: Hiring flag and company prose
- **WHEN** a YC payload has a hiring flag and a company marketing description
- **THEN** they remain separate fields and the description is not asserted to be a job specification or purchase request

#### Scenario: Inactive and zero-size input
- **WHEN** a valid payload is inactive and its reported team size is zero
- **THEN** both values are preserved without interpreting zero as absent or creating an eligible company

### Requirement: Separate source time from processing time

The system SHALL preserve known publication, source modification, launch, and
observation timestamps with their original meanings. Capture time SHALL be
recorded separately. Missing source times SHALL remain unknown; rerunning capture
SHALL NOT refresh event age. Observation metadata SHALL identify whether it is
payload-version-specific or only the latest record check.

#### Scenario: Old launch captured today
- **WHEN** a YC listing launched years ago is captured today
- **THEN** its launch remains historical and capture time does not become a fresh hiring event

#### Scenario: Repeated check metadata
- **WHEN** only an unchanged Bronze record's last-checked metadata advances
- **THEN** the existing content snapshot is reused and any new observation metadata does not rewrite its immutable content or invent version-specific history

### Requirement: Safe additive persistence and compatibility

The preservation workflow SHALL write only its new context/run records. It SHALL
NOT modify existing Bronze payloads, source-specific Silver descriptions,
resolution, Gold, operational matches, scores, or feedback. Failures SHALL be
reported per record with safe reasons; a run with failures SHALL NOT report full
success. Existing command behavior SHALL remain unchanged.

#### Scenario: Mixed valid and invalid inputs
- **WHEN** one record cannot be normalized while others can
- **THEN** valid outputs can be retained, failure is explicit, and existing pipeline data is unchanged

#### Scenario: Existing consumers
- **WHEN** capture is run over records already present in Silver and Gold
- **THEN** existing descriptions, IDs, match eligibility, and workflow state remain unchanged
