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
- Stage: String (source's own funding/development classification, free text; Type 1)
- CompanyStatus: String (registry lifecycle as the source spells it, free text. YC's vocabulary is Active/Inactive/Acquired/Public, but Acquired and Inactive are filtered out before Silver, so in practice this holds `Active`, `Public`, or NULL for a company only an HN signal knows about; Type 1)
- BusinessSector: List of Strings (multi-valued; YC's `industries` verbatim, order preserved, no Huginn-side taxonomy mapping, and the source's own `Unspecified` kept as-is; Type 2 tracked, see CompanyHistory)
- CompanyScale: Enum (0-10, 11-100, 101-1000, 1001+) (headcount bands derived from YC's `team_size`; Huginn's own vocabulary, not a source's, which is why the schema constrains it. Type 1)
- LegalForm: String (legal form, free text and jurisdiction specific, e.g. "Private Limited Company", "LLC", "C Corp". Renamed from CompanyType, which did not say what the column holds and sat among `company_`-prefixed columns on three unrelated axes. A different axis from CompanyScale; see architecture-notes/opencorporates-fetch-plan.md section 4)
- Country: String (parsed in Gold from YC's `all_locations` display string, first location's last comma segment; a bare `Remote` or an empty string yields no value rather than a guess; Type 1)
- City: String (parsed in Gold from YC's `all_locations`, first location's first comma segment; left null when a location names no city of its own, e.g. `Singapore, Singapore`; Type 1)
- Notes: String (nullable; free text about the company, each value opening with the source that supplied it, e.g. `YC Summer 2023`. One column rather than one per source per fact, because a second portal's batch, founding year, or registry field is inevitable, and the prefix keeps a reader able to tell whose statement it is while YC is the only source writing one: the prefix is hardcoded and is a label, not a merge key, so a second portal's value would overwrite this one and be labelled YC. Composed in Gold, not captured in Silver, because the prefix is Huginn's vocabulary. Type 1 with no `CompanyHistory` counterpart: a note is descriptive, so a change in wording is not a recorded attribute change)
- Address: String
- PhoneNumber: String
- Email: String
- TeamCompositionSignal: Enum (Unknown, LikelyNo, LikelyYes) (Type 2 tracked, see CompanyHistory)
- EuStartupsSearchedAt: DateTimeOffset (nullable; per-source enrichment pipeline cursor, not a Type 2 tracked company fact, see ADR-0010. Nothing writes it yet, so it is NULL for every row today and the ADR-0010 candidate gate cannot yet exclude an already-searched company)
- CurrentSince: DateTimeOffset (when the current set of Type 2 tracked values took effect)
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## CompanyHistory
One row per superseded version. Written only when a Type 2 tracked field on Company changes: the old values move here, the new values overwrite Company in place. Nothing in this table is ever current by definition, so no IsCurrent flag here either.
- Id: GUID
- CompanyId: GUID
- Domain: String (denormalized for convenience)
- BusinessSector: List of Strings
- TeamCompositionSignal: Enum (Unknown, LikelyNo, LikelyYes)
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
- Website: String (nullable; 178 of the 273 live `silver.hn_postings` rows carry no extractable URL, 65%)
- SignalType: Enum (Hiring, Funding, ProgramMilestone, Other)
- Stage: String (nullable)
- Description: String
- OccurredOn: DateTimeOffset (nullable)
- Url: String
- IngestedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## YcListingStaging (silver.yc_listings)
Holds only companies this tool can act on. A company whose YC `status` is `Acquired` or `Inactive` is landed in Bronze exactly as fetched and stays there, but the Silver parser declines to promote it, so a company first seen in an excluded state never reaches this table or anywhere downstream. `Public` is kept: a listed company is also not a prospect, but the rule is "no longer operating independently", not "not Active". A missing `status` is kept too, because absent means the source did not say, which is not the same claim as acquired.

The exclusion gates promotion and does not retract it. A company staged while `Active` and later reported `Acquired` keeps its existing row, because the loader skips the same `stable_id` and writes nothing for it; that row is removed only by a full Silver rebuild or an explicit delete, neither of which the current pipeline performs on every run. Live counts: 4,349 of 6,252 YC rows are staged, 1,903 skipped.
- Id: GUID
- StableId: String
- CompanyNameRaw: String
- Website: String (nullable)
- SignalType: Enum (Hiring, Funding, ProgramMilestone, Other)
- Stage: String (nullable)
- CompanyStatus: String (nullable; YC's registry lifecycle. Only `Active` or `Public` can appear here: `Acquired` and `Inactive` never reach Silver, see above)
- TeamSize: Integer (nullable; YC's headcount as an integer, *not* a band, see Company.CompanyScale)
- Industries: List of Strings (nullable; YC's `industries` verbatim and in source order. The singular `industry` key is not stored: it is `industries[0]` on every one of the 6,252 live `bronze.api_ingest` YC payloads, so it would be a derived duplicate. The plural key is present on all 6,252 of those payloads and on all 4,349 live `silver.yc_listings` rows, and not one of them is an empty array. NULL when the source omits the key, which is distinct from an empty list)
- AllLocations: String (nullable; YC's human-facing location display string, kept unparsed. Splitting it into Country and City is Gold's interpretation to own, the same reason `team_size` stays raw here and becomes `company_scale` there)
- FormerNames: List of Strings (nullable; YC's prior names, verbatim and not cleaned up, e.g. a self-referential `Leaders In Tech (formerly InnerSpace)` is kept as-is. Captured but not yet read by anything: recall needs name-based matching, which is KAN-4. On `silver.yc_listings` the column is non-null on all 4,349 live rows and 2,064 of those are an empty array rather than a list of names. NULL and empty stay distinct on purpose, NULL meaning the key was absent, which `_as_str_tuple` in `src/huginn/elt/silver/yc_staging.py` documents and why. 3,054 is a Bronze count, not a Silver one: that many of the 6,252 live `bronze.api_ingest` YC payloads carry at least one name)
- Batch: String (nullable; the funded batch the company joined YC in, as YC spells it, e.g. `Winter 2022`. 49 distinct live values in `silver.yc_listings`, spanning `Summer 2006` to `Winter 2027`, and 51 in `bronze.api_ingest`, spanning `Summer 2005` to `Winter 2027`. `Summer 2005` and `Winter 2006` are absent from Silver because every one of their rows is Acquired or Inactive and the parser declines those, so the two counts differ by exactly those batches. No live row in either table has a NULL batch, and exactly one, YC's own directory entry, reads `Unspecified`. That literal is one of the counts above rather than an addition to them, and it is stored as given rather than folded into null because the source stating it has no batch is a different claim from the key being absent.

  This is not `OccurredOn`, and the two are not interchangeable. `OccurredOn` carries YC's `launched_at`, which is when YC published the company, and the two dates are largely independent: the 90-company `Fall 2026` batch has 90 distinct `launched_at` values spanning 19 months, and every one of the eleven `silver.yc_listings` batches from `Summer 2006` to `Winter 2011` has its earliest `launched_at` on exactly 2012-01-17. Read the same range on `bronze.api_ingest`, which holds thirteen such batches, and one of them breaks the pattern: `Summer 2008`'s earliest is 2010-01-17, one row of that batch's 22, the other 21 sitting on 2012-01-17, and that one row is `Inactive`, which is why Silver never sees the exception. Airbnb's documented case is founded August 2008, batch `W09`, `launched_at` 2012-01-17. Three separate dates.

  No founding date exists on this source at all: YC's API payload carries none. The YC profile page does publish `year_founded`, but reaching it means a `web_scrape` of `ycombinator.com/companies/<slug>`, a different ingestion mechanism, not a column here)
- Description: String
- OccurredOn: DateTimeOffset (nullable)
- Url: String
- IngestedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

These six are YC-only: `CompanyStatus`, `TeamSize`, `Industries`, `AllLocations`, `FormerNames`, `Batch`. HN's freeform comments carry none of them, so these columns exist on this table alone rather than as nullable columns on every source's table (ADR-0001 anticipated exactly this case), and all six are NULL on every HN row of `silver.resolved_signals`. `HnPostingStaging` has the same shape minus these six.

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
- CompanyStatus: String (nullable; NULL for every HN row, which has no registry status)
- TeamSize: Integer (nullable; NULL for every HN row, which has no headcount)
- Industries: List of Strings (nullable; carried through from `YcListingStaging`, NULL for every HN row)
- AllLocations: String (nullable; carried through from `YcListingStaging` unparsed, NULL for every HN row)
- FormerNames: List of Strings (nullable; carried through from `YcListingStaging`, NULL for every HN row)
- Batch: String (nullable; carried through from `YcListingStaging`, NULL for every HN row)
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
