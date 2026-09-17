# 0010: EU-Startups enrichment gets its own candidate-selection column, not business_sector IS NULL

Status: Accepted
Date: 2026-09-17
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting, autonomous overnight run per explicit authorization, KAN-65)

## Context and Problem Statement

KAN-65 flags its own blocking design decision: `EnrichmentCandidatePort
.read_unenriched_company_names` (`gold/ports.py`, backing OpenCorporates,
KAN-53/54) gates on `business_sector IS NULL`, and its own docstring says
that column "doubles as never-enriched... designed for exactly one
enrichment source." KAN-65 needs the same shape of read, "which
gold.company rows has this adapter not tried yet," for a second, unrelated
source. Reusing the same gate as-is means whichever source's future writer
sets `business_sector` first (neither source's write side is built yet,
`CompanyWriter.write_all()` only ever writes `{"name": name}` today, see
`gold/company.py`) permanently and silently excludes that company from the
other source's candidate list, with no column recording which source did
it or whether the other source ever got a chance to try.

## Decision Drivers

1. `business_sector`'s null-ness is a Type 2 tracked company *fact* (ADR-0002,
   `dimensional.TYPE_2_TRACKED_FIELDS`), not a per-source pipeline cursor.
   Two different concepts sharing one column is exactly the ADR-0009
   Decision Driver 1 shape of problem again (`StatePort.last_hash` vs a
   crawl-level watermark), just recurring one layer up.
2. EU-Startups' own substring-collision search behavior (ADR context: a
   name search can return zero, one, or several matches, not always
   resolving to a clean single hit) means this source needs to record "I
   already looked, whatever the outcome" independently of whether it
   happened to also produce a `business_sector` value, so a company that
   never resolves to a single EU-Startups match isn't searched again every
   run forever.
3. OpenCorporates' existing candidate query and its callers
   (`ingestion/__main__.py`'s `load_opencorporates_companies`) must not
   need to change: this is an established, already-wired, already-working
   read, not a build in progress like KAN-64's discovery adapter.

## Considered Options

1. A new, dedicated `gold.company.eu_startups_searched_at TIMESTAMPTZ`
   column (nullable, NULL = never searched via this source), a new port
   method reading rows where it's NULL, set by this adapter's own writer on
   every search attempt regardless of outcome, entirely decoupled from
   `business_sector`. (chosen)
2. Extend `read_unenriched_company_names` to also gate on a second,
   generic per-source tracking table (`company_id`, `source`,
   `searched_at`), built now even though only one caller needs it.
3. Keep the shared `business_sector IS NULL` gate, and add an explicit
   priority rule (e.g. OpenCorporates always runs first; EU-Startups only
   considers companies OpenCorporates has already given up on).
4. Do nothing: let both sources share the gate as today, accept that
   whichever runs first excludes the other.

## Decision Outcome

Chosen option: 1, a new source-specific column. It resolves KAN-65's stated
blocker with the smallest change that doesn't touch OpenCorporates' already
-working read path at all (Decision Driver 3), and doesn't build a generic
multi-source tracking table (option 2) for a codebase with exactly two
enrichment sources today, one of them (KAN-42/43) not even at build stage
yet, CLAUDE.md code standard 6 (scope discipline). It is written outside
`apply_company_update`'s Type 1/2 dimensional flow entirely: it is pipeline
metadata (like `stable_id` in ADR-0007, or `ingested_at` at Bronze), not a
company fact a downstream scoring read or `company_history` row needs, so
it is set with a direct, single-column update rather than routed through
`write_company`.

### Consequences

1. Good: OpenCorporates' `read_unenriched_company_names` and its caller are
   untouched, zero regression risk to an already-wired, working path.
2. Good: EU-Startups' candidate selection and OpenCorporates' candidate
   selection are fully independent; either source can be added, removed, or
   re-run without affecting the other's view of what's left to enrich.
3. Good: a company where EU-Startups' search never resolves to exactly one
   match (the substring-collision case) still gets marked searched, so it
   is not re-fetched and re-filtered every run forever, matching Decision
   Driver 2.
4. Neutral: if both sources eventually write `business_sector` for the same
   company (once KAN-65's and a future OpenCorporates writer both exist),
   whichever runs later wins under `apply_company_update`'s existing
   compare-and-replace Type 2 logic, same last-write-wins semantics any
   Type 2 tracked field already has under concurrent sources; no new merge
   or precedence logic is introduced by this ADR, and none is needed yet
   with no evidence either source's value would conflict in practice.
5. Bad: a second nullable timestamp column on `gold.company` whose only
   consumer is this one adapter, the same "protocol/column before its
   second user exists" shape this codebase already treats as normal
   (ADR-0009 Decision Driver 3), not a new kind of gap.
6. Neutral: any future third enrichment source (KAN-42/43's team-composition
   signal, still at design stage) should follow this same pattern, its own
   dedicated candidate-tracking column, not a reuse of this one or of
   `business_sector IS NULL`; noted here so that decision doesn't need
   re-litigating from scratch.

## Pros and Cons of the Options

### Option 1: a new, dedicated `eu_startups_searched_at` column (chosen)

1. Good: zero change to OpenCorporates' existing, working candidate query.
2. Good: correctly separates "has this company's business_sector been set"
   (a fact) from "has this source already tried" (a per-source cursor).
3. Good: minimal, one column, one query, no new table or generic mechanism.
4. Bad: a column with exactly one consumer today.

### Option 2: a generic per-source tracking table now

1. Good: scales cleanly to a third, fourth source without another ADR.
2. Bad: builds generality (CLAUDE.md code standard 6, design standard 6)
   for a second use case that doesn't exist yet (KAN-42/43 is still at
   design stage); no real requirements yet for what such a table needs
   beyond "company + source + timestamp," the same "guess now vs. decide
   with real requirements" question ADR-0009 already answered by deferring.

### Option 3: an explicit cross-source priority/ordering rule

1. Good: keeps one shared gate, no new column.
2. Bad: makes each source's candidate set depend on the other's run order
   and outcome, a real coupling between two otherwise-independent adapters
   for no benefit this ticket's scope needs.
3. Bad: does not solve Decision Driver 2 (EU-Startups needs to remember a
   substring-collision search attempt regardless of what OpenCorporates did).

### Option 4: do nothing, accept the silent exclusion

1. Good: zero implementation cost.
2. Bad: exactly the bug KAN-65's own ticket text flags as blocking, a
   company enriched by whichever source happens to run first permanently
   and silently hides from the other, with no record of which source
   decided or whether the other ever got a chance.

## Related

1. `gold/ports.py`'s `EnrichmentCandidatePort.read_unenriched_company_names`:
   the existing, OpenCorporates-only gate this ADR does not change.
2. ADR-0009: the same "one shared mechanism serving two unrelated
   questions" shape of problem, resolved the same way, one layer down the
   pipeline.
3. ADR-0007's `source_stable_id` precedent: a plumbing/identity column
   introduced ahead of its second real consumer, not routed through the
   dimensional Type 1/2 update flow.
4. KAN-53/54 (OpenCorporates enrichment, the first caller of the shared
   gate this ADR stops overloading), KAN-65 (this decision's ticket),
   KAN-42/43 (a future third enrichment source that should follow this same
   pattern, not reopen this decision).
