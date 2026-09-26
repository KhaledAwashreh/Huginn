# OpenCorporates Adapter Fetch Plan (KAN-53)

Translates `docs/sources/opencorporates-api.md` into the concrete choices `src/huginn/elt/ingestion/adapters/opencorporates.py`'s `fetch()` needs to be implemented against (KAN-54). Cites that document by section rather than restating its research.

**Unlike `docs/sources/opencorporates-api.md` and the YC/HN fetch plans, the response shape below is not independently confirmed live.** No API token was registered for this session (2026-09-13 design discussion: the free tier's share-alike open-data licence doesn't fit this project's eventual commercial use, so a free-tier token was judged not worth registering just to test with). The search response envelope described in section 2 is OpenCorporates' documented public convention, not a live-verified shape. This must be confirmed against a real call before this adapter is trusted with a real run; treat every `payload["results"]["companies"]`-shaped access in the implementation as provisional until then.

## 1. Discovery vs. enrichment: enrichment only

Decision: this adapter enriches companies Huginn already knows about (via Silver/Gold's HN/YC resolution), it does not discover new ones independently.

Reasons:

1. `docs/sources/opencorporates-api.md`, Open questions/risks: `companies/search` requires a `q` name-search term; there is no filter-only "all new companies in country X" browse endpoint. Nothing in the API supports a discovery query shape at all.
2. Even if one existed, the free-tier quota (200/month, 50/day — `docs/sources/opencorporates-api.md`, Access) cannot sustain open-ended discovery. It can sustain a small, bounded number of lookups against companies already identified elsewhere.
3. This is an explicitly deferred choice, not a permanent one: Jira KAN-58 tracks revisiting discovery mode once enough real HN/YC data has been ingested to judge whether enrichment-only sourcing is enough on its own.

## 2. Endpoint: `companies/search?q=<name>`, not a targeted jurisdiction/number lookup

Decision: query `GET /v0.4/companies/search?q=<company_name>&api_token=...`, not `GET /v0.4/companies/:jurisdiction_code/:company_number`.

Reasons:

1. An HN/YC-sourced company gives Huginn a name (`gold.company.name`) and a domain, never a jurisdiction code or registry company number. The targeted lookup endpoint needs both of those as path parameters (`docs/sources/opencorporates-api.md`, Response shape); nothing upstream can supply them, so that endpoint isn't reachable on a first pass.
2. Search-by-name is the only endpoint shape that takes what's actually available.

**Response shape (documented convention, not live-verified — see the flag at the top of this note):** OpenCorporates' public API wraps every response body under a top-level `"results"` key. For `companies/search`, the documented convention is `results.companies`, a list where each entry is `{"company": {...full company detail fields...}}`, alongside `results.page`/`results.per_page`/`results.total_pages`/`results.total_count`. This structure needs a real, live-confirmed call before being trusted; the implementation isolates every access to this shape behind one small parsing function so a shape correction, if the live structure differs, is a one-function fix, not a scattered one.

## 3. Match ambiguity: exactly one confident hit enriches, anything else skips

Decision: a search that returns exactly one result enriches that company. Zero results, or more than one, skips enrichment for that company this run (no guess, no partial-confidence fallback).

Reasons:

1. `companies/search` is a fuzzy name search, not an exact-match lookup (`docs/sources/opencorporates-api.md`, Response shape: "Company search filtering is genuinely powerful," implying relevance-ranked results, not deterministic identity resolution). A common name ("Acme") plausibly matches multiple unrelated companies across the ~140+ jurisdictions OpenCorporates aggregates.
2. This mirrors an existing, working precedent in this codebase: `huginn.elt.silver.signal_resolution.resolve_signal` treats an ATS/platform host as "no match" rather than a wrong confident one, on the stated principle that a wrong match is worse than none. The same principle applies here: writing OpenCorporates data for the wrong company would corrupt `gold.company`, not just leave a gap.
3. A skipped company is not lost. It stays selected by the next run's query (section 5) until it either resolves to exactly one hit or the run budget is spent trying.

## 4. Field mapping: officers and ownership excluded, `company_type` maps cleanly

Decision: `RawRecord.payload` carries the matched company object close to
as returned (see `docs/sources/opencorporates-api.md`, Response shape, "Company
detail record" field list), with the privacy-safe exception that this adapter
removes the top-level `officers` field before Bronze persistence. The adapter
does not mutate the API response object. Its structured field selection (what
Silver eventually maps out of the payload, a later ticket's scope) settles
three source fields:

- **`officers`**: `docs/sources/opencorporates-api.md`'s Open questions/risks flags this as containing names, positions, sometimes dates of birth and home addresses. No data-retention policy exists yet for that class of data, independent of and separate from the licensing question KAN-12 already accepted. It is therefore removed from the Bronze payload at `_company_record`, rather than merely excluded from later structured use.
- **`controlling_entity`, `ultimate_beneficial_owners`, `ultimate_controlling_company`, `corporate_groupings`**: genuinely new signal (parent/ownership structure), not something the original proposed mapping in `docs/sources/opencorporates-api.md` accounted for. Jira KAN-57 is the dedicated epic for deciding what, if anything, Huginn should do with this; this adapter's job is only to not lose the data (it survives in `raw_payload` regardless), not to design its use.
- **OpenCorporates' `company_type`**: the one source field with a genuine,
  non-conflicting fit, because it is a legal form ("Private Limited Company",
  "LLC") and `gold.company.legal_form` holds exactly that: free text,
  jurisdiction specific, unconstrained. It did not always, and the reasoning
  is worth keeping. When this note was written `gold.company.company_type` was
  `CHECK (company_type IN ('enterprise', 'startup', 'sme'))`, a
  size/structure classification, so mapping a legal form onto it would have
  silently corrupted the column rather than merely under-populating it.
  `db/schema/gold-company-scale.sql` split that one overloaded column in two:
  the size axis became `company_scale`, constrained to the four headcount
  bands `0-10`, `11-100`, `101-1000`, `1001+`, and what was left holding
  legal forms was renamed `legal_form` by
  `db/schema/gold-rename-company-type-to-legal-form.sql`. `legal_form` is NULL
  on all 4,423 live rows and no writer in the tree sets it, so nothing has
  gone through it yet; that is a queue state, not a reason to withhold the
  mapping. The hazard recorded here still stands for whoever writes the
  column: `legal_form` and `company_scale` are different axes and neither
  may be derived from the other.

Fields with a genuine, non-conflicting fit among the other `gold.company`
columns: `industry_codes` → `business_sector`,
`registered_address_in_full`/`jurisdiction_code` → `address`/`country`/`city`.
`business_sector`, `country` and `city` were all empty when this note was
written and are now populated from YC, on 4,337, 4,244 and 4,196 of the 4,423
live rows respectively; `address` is still empty on all 4,423. `business_sector`
is Type 2 tracked, so a differing value written there for a company that
already has a row supersedes that row into `gold.company_history`, which is a
decision for the writer that fills it, not for this adapter. Actually writing
any of these into Gold is out of this ticket's scope (see section 7); this
section only settles what this adapter's own field selection does and does not
carry forward.

## 5. Company selection: read `gold.company` for never-enriched rows

Decision: the adapter's target company list comes from `gold.company` (specifically, rows with `business_sector IS NULL`, ordered oldest-created first), not from `silver.resolved_signals` directly.

Reasons:

1. `gold.company` is already the deduplicated, one-row-per-domain table (`db/schema/gold.sql`; built by KAN-40). Reading from `silver.resolved_signals` instead would mean re-deriving that dedup (the same domain can appear across many event-grain signal rows — this exact redundancy was a finding fixed in KAN-40's own review, `src/huginn/elt/gold/company.py`'s domain-collapse logic).
2. `business_sector IS NULL` doubles as "never successfully enriched yet," with no separate enrichment-status column needed. This is also this build's entire selection/prioritization strategy for now: oldest-first, capped by the run's call budget — not a scoring-informed selection (that's not buildable yet; KAN-8's scoring logic doesn't exist), and explicitly not meant to be the final answer (see the quota-math note below).

**Worth naming plainly, not treated as a design flaw to fix now:** this makes the adapter read Gold to decide what to fetch into Bronze, which runs backward against the pipeline's normal Bronze → Silver → Gold direction. It's confined to the CLI composition root (`src/huginn/elt/ingestion/__main__.py`, which already constructs cross-layer Postgres objects directly), not leaked into `IngestionService` or any core orchestration logic, so it's a wiring-level exception, not an architectural rule change.

**Quota reality**, worth stating plainly rather than optimistically: 200 free-tier calls/month against a real single ingestion run's 6,253 `domain_normalized` resolved signals means the current backlog alone would take over two years to clear at that rate, before counting new signals arriving every run. Oldest-first selection is a placeholder ordering, not a considered prioritization strategy; a real one waits on scoring existing (KAN-8) so "which 200 companies this month" can be an actual decision instead of an arbitrary one. This is exactly the kind of thing this build is deliberately not solving now, per the "build it cheap, decide usefulness later" call made in this session.

## 6. `stable_fields` for Bronze's content hash

Decision: `["current_status", "dissolution_date", "updated_at"]`.

Reasoning: `huginn.elt.bronze.watermark.compute_content_hash` exists to answer "did this record's real-world state change since last fetch," excluding volatile fields that would make every re-fetch look changed (`huginn.elt.bronze.watermark`'s own module docstring; the same problem HN's `score`/`descendants` and YC's Algolia relevance ranking already have, and why neither adapter has ever passed a real `stable_fields` subset — both currently hash the entire payload, tracked separately as KAN-47's core finding). For a re-fetched OpenCorporates company record, the fields that represent an actual state change, not incidental API noise, are whether it's still active (`current_status`), whether it's since been dissolved (`dissolution_date`), and OpenCorporates' own "something about this record changed" signal (`updated_at`, per `docs/sources/opencorporates-api.md`'s Freshness/cadence section). `industry_codes`/`registered_address`/other structural fields are expected to be stable once a company is enriched, not the boundary of what "changed" means here.

This adapter's use of real `stable_fields` is the first to actually exercise that code path (HN/YC both pass `sorted(payload.keys())`, hashing everything). Doing so activates a latent bug already diagnosed on KAN-47's comment thread: `compute_content_hash` hashes `payload.get(field, "")` per field, so a field missing from the payload and a field present-but-explicitly-empty hash identically, silently masking a real change if a field appears or disappears between fetches. This build fixes that alongside adding the first real `stable_fields` caller, rather than shipping a known bug live for the first time it would actually fire (KAN-47's own broader stable_fields redesign for HN/YC stays open separately; this only fixes the shared hashing function's presence-blindness, a small, isolated, already-diagnosed correctness fix, not a redesign of HN/YC's hashing choices).

## 7. What this ticket does not do

Explicitly out of scope for KAN-53/54, matching KAN-54's own ticket text ("mirroring HackerNewsAdapter/YcDirectoryAdapter's shape" — an ingestion adapter, nothing more):

- No Silver staging step for `bronze.api_ingest` rows with `source = "opencorporates"`. Nothing currently reads them back out of Bronze.
- No write-back into `gold.company`'s `business_sector`/`country`/`city`/`address` columns. Of those four only `address` is still empty; the other three are populated from YC since this note was written (section 4). Section 4 names the field-fit; actually wiring it through Silver/Gold is real, separate scope, not yet ticketed.
- No stateful monthly/daily quota tracking against `GET /account_status` (`docs/sources/opencorporates-api.md`, Access). This build takes a simple per-run call budget (a constructor parameter), not a cross-run persistent tracker.

These are natural follow-up tickets once real OpenCorporates data has actually been looked at (matching this session's "build it cheap, decide usefulness later" reasoning) — not oversights.

## Reference

`docs/sources/opencorporates-api.md` (Access, Response shape, Signal mapping, Open questions/risks). `src/huginn/elt/ingestion/{models,ports}.py` (`RawRecord`, `ApiSourcePort`). `src/huginn/elt/ingestion/adapters/yc.py` (closest existing adapter pattern). `src/huginn/elt/bronze/watermark.py` (`compute_content_hash`, the field-presence bug this build fixes). `src/huginn/elt/gold/repositories/company_repository.py`, `src/huginn/elt/gold/ports.py` (existing `gold.company` read pattern this build's new selection query mirrors). `db/schema/gold.sql` (the legal-form versus size semantic mismatch, and which enrichable columns are still empty). Jira KAN-53 (this note), KAN-54 (consumes it), KAN-57 (parent/ownership signal epic), KAN-58 (discovery-mode revisit), KAN-47 (the broader stable_fields/hashing debt this build partially closes), KAN-12 (licensing, unaffected by this build).
