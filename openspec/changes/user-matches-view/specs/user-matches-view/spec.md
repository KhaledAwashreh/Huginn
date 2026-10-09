## Purpose

Give authenticated users a safe, read-only view of their own existing company matches, with current public company and signal context clearly distinguished from the historical reason a match was created.

## ADDED Requirements

### Requirement: User can browse their own matches
The system SHALL provide an authenticated paginated list of only the current user's `operational.match` records, joined to the corresponding current `gold.company` fields. Each item SHALL expose match ID, status, match creation and update timestamps, existing notes, and company name, domain, sectors, country, size, and status. The list SHALL accept an optional existing match status as a filter, order by match creation time descending and match ID descending as a stable tie-breaker, and cap each page at 100 items.

#### Scenario: List defaults to the newest owner matches
- **WHEN** an authenticated user requests the first match page without a status filter
- **THEN** the response contains only that user's matches, includes current company fields, and orders rows by match creation time descending then match ID descending

#### Scenario: List filters by a valid match status
- **WHEN** an authenticated user requests a match page with a supported status filter
- **THEN** every returned match has that status and pagination remains bounded to at most 100 items

#### Scenario: List rejects invalid filters and page bounds
- **WHEN** a request supplies an unsupported status, a page limit below 1 or above 100, or a negative offset
- **THEN** the API returns a validation error without returning match data

#### Scenario: Empty list is a successful page
- **WHEN** an authenticated user has no matches for the selected status and page
- **THEN** the API returns an empty item collection with valid pagination metadata

### Requirement: User can read only an owned match and its current signals
The system SHALL provide an authenticated detail read for a match only when its `user_id` is the current user. The detail SHALL include the same match and current company fields as the list. A separate paginated read SHALL expose only the current `gold.company_signal` rows for that owned match's company, with signal ID, type, source, source URL, description, stage, occurrence time, and ingestion time. Signals SHALL be ordered by occurrence time descending and signal ID descending and each page SHALL be capped at 100 items. A missing or other user's match SHALL return the same not-found response.

#### Scenario: User opens an owned match
- **WHEN** an authenticated user requests a match ID they own
- **THEN** the API returns its existing match details and current company fields

#### Scenario: User requests another user's match
- **WHEN** an authenticated user requests a match ID owned by another user or a nonexistent match ID
- **THEN** the API returns the same not-found response without disclosing whether another user's match exists

#### Scenario: User reads the current signals for an owned match
- **WHEN** an authenticated user requests a page of signals for a match they own
- **THEN** the API returns only current signals for that match's company, ordered by occurrence time descending then signal ID descending, with pagination bounded to at most 100 items

#### Scenario: Signals cannot be queried through an arbitrary company identifier
- **WHEN** a client attempts to select signals by supplying a company ID without an owned match
- **THEN** no such API operation is available and no signal data is returned

### Requirement: Private match read responses are not cacheable
Every response from the authenticated match list, detail, signals, and overview GET endpoints SHALL include `Cache-Control: no-store` and `Vary: Cookie`, including successful responses and authentication, authorization, not-found, validation, and server-error responses.

#### Scenario: Successful private match read is not cacheable
- **WHEN** an authenticated request to any match GET endpoint succeeds
- **THEN** the response includes `Cache-Control: no-store` and `Vary: Cookie`

#### Scenario: Private match read error is not cacheable
- **WHEN** a match GET endpoint returns an authentication, authorization, not-found, validation, or server error
- **THEN** the error response includes `Cache-Control: no-store` and `Vary: Cookie`

### Requirement: Match reads never perform writes or matching
The match list, detail, signal, and overview operations SHALL be read-only. They SHALL NOT create or update matches, change status or notes, create activities or communications, trigger matchmaking, or accept a user-selected company identifier as an execution target.

#### Scenario: Reading match pages leaves operational state unchanged
- **WHEN** an authenticated user reads the list, detail, signal pages, and overview
- **THEN** the system performs no database writes and does not start or enqueue a matching run

#### Scenario: No match action implies a status mutation
- **WHEN** a user views a match in any supported state
- **THEN** the workspace offers no status, note, activity, communication, or dismissal write action

### Requirement: Overview explains empty states from owner-scoped durable state
The system SHALL provide an authenticated read-only overview scoped to the current user. It SHALL report whether that user has any matches across all statuses and pages (`has_matches`), whether that user has any active discovery strategy, and a summary of the latest durable per-user managed matchmaking result when the authoritative run projection is available. It SHALL distinguish no active strategy, no recorded managed evaluation, and an acknowledged successful evaluation that created zero new matches. It SHALL NOT describe the absence of managed run history as proof that matching never ran, because legacy CLI executions are not recorded in the managed run projection. Existing match rows SHALL remain visible regardless of the latest run's number of new matches. Pending, running, stale, failed, missing, or unavailable evaluation evidence SHALL be represented as unknown or unavailable and SHALL NOT be presented as a definitive zero-result evaluation. Result counts SHALL be exposed only for an acknowledged successful per-user outcome.

#### Scenario: User has no active discovery strategy
- **WHEN** the authenticated user's overview is requested and the user has no active strategies
- **THEN** the overview reports no active strategy and does not claim that a matchmaking evaluation found no qualifying companies

#### Scenario: User has active strategies but no managed run is recorded
- **WHEN** the authenticated user has an active strategy and no managed per-user run result is recorded
- **THEN** the overview reports that no managed evaluation is recorded and does not claim that matching never ran or that an evaluation had zero results

#### Scenario: Latest completed evaluation created no new matches
- **WHEN** the authenticated user's latest durable completed evaluation created zero matches
- **THEN** the overview reports a completed zero-new-match evaluation and preserves any existing matches in the list

#### Scenario: Overview reports matches across all statuses and pages
- **WHEN** the authenticated user has at least one match, including one outside the current list status filter or page
- **THEN** the overview reports `has_matches: true` based on all of the user's match rows, independent of the current list query

#### Scenario: Evaluation evidence is incomplete, stale, or unavailable
- **WHEN** the latest run is pending, running, stale, failed, has no owner result, or the durable run projection cannot establish an acknowledged successful evaluation result
- **THEN** the overview reports an unknown or unavailable evaluation state and does not present a definitive no-results conclusion

#### Scenario: Overview is isolated by authenticated owner
- **WHEN** one user requests the overview
- **THEN** its active-strategy and run-result data are derived only from that authenticated user's records

### Requirement: Matches workspace distinguishes current context from match qualification
The browser workspace SHALL provide a Matches list at `/matches` and an owned match detail at `/matches/:id`. It SHALL show current company attributes and current company signals as present-day context, and SHALL NOT describe them as the evidence or rationale that originally qualified the match. Existing match notes MAY be displayed as stored text. The workspace SHALL NOT invent a score, qualification reason, or historical signal attribution.

#### Scenario: User views current company and signal context
- **WHEN** a user views an owned match detail
- **THEN** the UI labels company attributes and signal rows as current company context and does not claim that they explain the original match qualification

#### Scenario: Match has no stored notes or current signals
- **WHEN** an owned match has null notes or no current signals
- **THEN** the detail shows an appropriate empty value without inventing notes, signals, score, or rationale

#### Scenario: Company and source links are safe
- **WHEN** the UI renders a company domain or signal source URL as a link
- **THEN** it creates an external link only for a valid HTTP or HTTPS URL or a safely constructed HTTPS company-domain URL, rejects unsafe schemes and malformed or nested URL values, and never treats source text as trusted HTML

#### Scenario: List and detail handle load and failure states
- **WHEN** match data is loading, the user has no matches, or a request fails
- **THEN** the workspace presents the corresponding accessible loading, contextual empty, or error state and offers retry after a recoverable read failure

#### Scenario: Selected status has no matches in the requested page
- **WHEN** a match page is empty while a status filter is selected
- **THEN** the UI identifies that the selected filter/page has no rows and offers to clear the filter or return to the first page without implying that the user has no matches overall or that evaluation is pending

#### Scenario: Requested page is out of range while owner matches exist
- **WHEN** an unfiltered match page is empty at a nonzero offset and the overview reports `has_matches: true`
- **THEN** the UI identifies that the requested page has no rows and offers to return to the first page without showing the overall empty state or implying that evaluation is pending

#### Scenario: Overall empty state requires owner-wide absence of matches
- **WHEN** the unfiltered first match page is empty and the overview reports `has_matches: false`
- **THEN** the UI may explain the overall empty state from active-strategy and latest-result context

#### Scenario: Terminal read errors are not retried automatically
- **WHEN** a match GET returns 401, 403, 404, or 422
- **THEN** the workspace does not automatically retry the request and follows the shared session and error handling behavior
