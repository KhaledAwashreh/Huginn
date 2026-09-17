# Operational

## Account

Authentication credentials and account lifecycle only. `Account` does not own
personal, professional, targeting, or matching data.

- Id: GUID
- Username: String (trimmed spelling, case-insensitive unique index)
- PasswordHash: String
- Status: Enum (Active, Disabled)
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## User

Mandatory personal and contact information. `AccountId` is the unique
ownership key to Account. `User.Id`, not Account.Id, is the ownership key for
professional and business-domain data. The existing `Match.UserId` therefore
continues to reference User.

- Id: GUID
- AccountId: GUID (unique foreign key to Account)
- FirstName: String
- LastName: String
- Email: String
- PhoneNumber: String
- CountryOfResidence: String
- Timezone: String (nullable)
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## ProfessionalProfile

The intended lifecycle has one profile per User. `UserId` is the unique
ownership key, which enforces at most one profile; KAN-72 must create the
profile atomically with Account and User to make it mandatory. Skills,
experience, and previous projects are validated arrays of structured objects,
never null, and default to empty arrays. Their complete object contract is in
the [management foundation](management-foundation.md).

- Id: GUID
- UserId: GUID (unique foreign key to User)
- Headline: String (nullable)
- ProfessionalSummary: String (nullable)
- Skills: JSON array
- Experience: JSON array
- PreviousProjects: JSON array
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

# Gold

## Company
Current state only. One row per company, always. Overwritten in place when any field changes, including the Type 2 tracked fields below (see ADR-0002). No IsCurrent flag and no ValidTo needed here: there is nothing else in this table to filter out.
- Id: GUID
- Domain: String (durable natural key from entity resolution)
- Name: String
- BusinessSector: String (Type 2 tracked, see CompanyHistory)
- CompanyType: Enum (Enterprise, Startup, SME)
- Country: String
- City: String
- Address: String
- PhoneNumber: String
- Email: String
- TeamCompositionSignal: Enum (Unknown, LikelyNo, LikelyYes) (Type 2 tracked, see CompanyHistory)
- IcpFilterPass: Boolean (Type 2 tracked, see CompanyHistory)
- CurrentSince: DateTimeOffset (when the current set of Type 2 tracked values took effect)
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## CompanyHistory
One row per superseded version. Written only when a Type 2 tracked field on Company changes: the old values move here, the new values overwrite Company in place. Nothing in this table is ever current by definition, so no IsCurrent flag here either.
- Id: GUID
- CompanyId: GUID
- Domain: String (denormalized for convenience)
- BusinessSector: String
- TeamCompositionSignal: Enum (Unknown, LikelyNo, LikelyYes)
- IcpFilterPass: Boolean
- ValidFrom: DateTimeOffset
- ValidTo: DateTimeOffset

## CompanySignal
- Id: GUID
- CompanyId: GUID
- SignalType: Enum (Funding, Hiring, ProgramMilestone, Expansion, Leadership, Other)
- Source: String
- SourceStableId: String (unique with Source, ADR-0007: reuses ResolvedSignal's own natural key so a re-run upserts instead of duplicating)
- SourceUrl: String
- Stage: String (nullable)
- Description: String
- OccurredOn: DateTimeOffset
- IngestedOn: DateTimeOffset

## Employee
- Id: GUID
- CompanyId: GUID
- Name: String
- Position: String
- PhoneNumber: String
- Notes: String
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## Match
- Id: GUID
- UserId: GUID
- CompanyId: GUID
- Status: Enum (New, Contacted, Responded, Dismissed, Converted)
- Notes: String
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## MatchScore
- Id: GUID
- MatchId: GUID
- ScoringAlgorithm: Enum
- Score: Integer
- FeatureBreakdown: JSON
- ScoredOn: DateTimeOffset

## MatchFeedback
- Id: GUID
- MatchId: GUID
- Rating: Enum (Positive, Negative)
- GivenOn: DateTimeOffset

## Activity
- Id: GUID
- MatchId: GUID
- EmployeeId: GUID (nullable)
- Type: Enum (Note, EmailSent, CallMade, FollowUpPlanned, ...)
- DueOn: DateTimeOffset (nullable)
- CompletedOn: DateTimeOffset (nullable)
- Notes: String
- OccurredOn: DateTimeOffset
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## Communication
- Id: GUID
- MatchId: GUID
- Channel: Enum (Email, LinkedIn, Other)
- Subject: String (nullable)
- Status: Enum (Drafting, Finalized, Sent)
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## CommunicationVersion
- Id: GUID
- CommunicationId: GUID
- VersionNumber: Integer
- Content: String
- IsFinal: Boolean
- CreatedOn: DateTimeOffset

## CommunicationRevision
- Id: GUID
- CommunicationVersionId: GUID
- DerivedFromVersionId: GUID (nullable)
- AgentType: Enum (User, AI)
- ChangeSummary: String
- OccurredOn: DateTimeOffset

## CommunicationTurn
- Id: GUID
- CommunicationRevisionId: GUID
- Role: Enum (User, Assistant)
- Content: String
- CreatedOn: DateTimeOffset

# Silver

Per-source staging tables, one per source, all sharing this shape — conformed to a common structure but not yet merged across sources. Current-state upsert, no version history. Bronze holds only the latest raw payload per entity too (overwrite in place on a hash change, `UNIQUE (source, stable_id)`), not full history.

## HnPostingStaging (silver.hn_postings)
- Id: GUID
- StableId: String
- CompanyNameRaw: String
- Website: String (nullable — ~11% of sampled HN posts have no extractable URL)
- SignalType: Enum (Hiring, Funding, ProgramMilestone, Other)
- Stage: String (nullable)
- Description: String
- OccurredOn: DateTimeOffset (nullable)
- Url: String
- IngestedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## YcListingStaging (silver.yc_listings)
- Id: GUID
- StableId: String
- CompanyNameRaw: String
- Website: String (nullable)
- SignalType: Enum (Hiring, Funding, ProgramMilestone, Other)
- Stage: String (nullable)
- Description: String
- OccurredOn: DateTimeOffset (nullable)
- Url: String
- IngestedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

(Additional per-source staging tables follow this same shape as sources are added.)

## ResolvedSignal (silver.resolved_signals)
Fed by all staging tables together. Still event grain — one row per original signal — deliberately *not* split into separate company and signal tables; that dimensional split is Gold's job (see `architecture-notes/industry-references-elt-medallion.md`). `ResolvedCompanyKey` is a plain resolved identity value here (the normalized domain, or a deterministic key from the fuzzy-match fallback), not a foreign key into a materialized company table — Gold builds the `Company` dimension from the distinct keys found in this table.
- Id: GUID
- SourceStableId: String
- Source: String
- ResolvedCompanyKey: String
- CompanyNameRaw: String
- SignalType: Enum (Hiring, Funding, ProgramMilestone, Other)
- Stage: String (nullable)
- Description: String
- OccurredOn: DateTimeOffset (nullable)
- Url: String
- KeyDerivation: Enum (DomainNormalized, FuzzyMatched, Unresolved) — how `ResolvedCompanyKey` was derived for this row: a normalized domain (one-sided candidate-key derivation, not a comparison against anything), a Jaro-Winkler ≥0.92 fuzzy match against an existing company (KAN-4, unbuilt), or no reliable key at all (synthetic placeholder, queued for manual review)
- ResolvedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## ManualReviewCandidate (silver.manual_review_queue)
- Id: GUID
- ResolvedSignalId: GUID
- CandidateCompanyKey: String
- MatchScore: Decimal
- Status: Enum (Pending, Confirmed, Rejected)
- CreatedOn: DateTimeOffset
- ReviewedOn: DateTimeOffset (nullable)

# Bronze

Three tables, grouped by ingestion mechanism rather than by individual source — `Source` distinguishes rows within each. All three share this exact shape; mechanism determines table membership, not a column. Append-only in spirit, but a fetch whose `ContentHash` matches the existing row for that `(Source, StableId)` doesn't insert a new row — it only bumps `LastCheckedOn`. Unique constraint: `(Source, StableId)` per table.

## ApiIngest (bronze.api_ingest)
- Id: GUID
- Source: String (e.g. "hn", "yc")
- StableId: String
- Payload: JSON
- ContentHash: String (SHA-256, over a stable field subset chosen per source, lightly normalized)
- FetchedOn: DateTimeOffset
- LastCheckedOn: DateTimeOffset
- RunId: GUID

## WebScrapeIngest (bronze.web_scrape_ingest)
- Id: GUID
- Source: String
- StableId: String
- Payload: JSON
- ContentHash: String
- FetchedOn: DateTimeOffset
- LastCheckedOn: DateTimeOffset
- RunId: GUID

## NewsletterIngest (bronze.newsletter_ingest)
- Id: GUID
- Source: String
- StableId: String
- Payload: JSON
- ContentHash: String
- FetchedOn: DateTimeOffset
- LastCheckedOn: DateTimeOffset
- RunId: GUID
