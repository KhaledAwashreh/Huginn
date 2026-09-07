# Huginn — ELT Pipeline & Digest Scoring Design (Grilling Session, 2026-09-05)

**Context:** Follow-on grilling session to the Sept 2026 scope-decisions session (see `huginn_mvp_scope_decisions` memory). Started as a session on digest scoring/weighting (Jira KAN-8), pivoted at the user's request to focus on the Bronze→Silver→Gold ELT pipeline and the matching step, since that's the immediate build priority. Digest-scoring phasing decisions made before the pivot are preserved below since they remain valid, just not the current build focus.

**Status:** Draft — queued for an auditor/fixer agent-pair review before being folded into the main Huginn Architecture Document.

---

## 1. Digest / scoring model — phasing

Resolved before the session pivoted to pipeline design. Still valid, not yet being built.

- **Composite scoring ships in phases, not as a single build.** v0 launches with no weighted composite score at all — ranking is by recency alone (freshest qualifying signal first) among companies that already passed the ICP pre-filters (stage/sector/recency, locked in the prior session). v1 adds a real weighted composite once there's real filtered-data volume to design feature weights against.
  - **Why:** inventing weights today, with zero historical `MatchFeedback` data, would just be guessing. Recency-only ranking is free (falls out of the filtering step) and still produces a useful, defensible order.
- **v0 is a shippable interim product**, not a throwaway spike — it sends real digests and starts generating the first real usage data that eventually informs v1's weights.
- **Visible ranking, but not a fabricated number.**
  - v0: show the plain underlying signal in the digest ("posted 2 days ago" / "raised Series A 11 days ago") — no manufactured score.
  - v1: a qualitative tier ("Strong / Good / Fair match"), not a raw number — a bare "73/100" implies precision the weights won't actually have, especially before any feedback-driven validation exists.
- **Score persistence:** a `Match` row's score/rank snapshots at creation time. Once a `Match` is `Sent`, its score is frozen permanently — never recomputed or revised. This is required for any future feedback-loop analysis to compare against what the user actually saw, not a revised-in-hindsight number.
- **Recompute (pending Matches only):** a still-pending Match's score can be recomputed, triggered by (a) new/late-arriving feature data (e.g. enrichment finishing after initial Match creation) or (b) global weight retuning once `MatchFeedback` data exists. Each recomputation is versioned (append-only history, e.g. a `MatchScoreHistory` table) rather than overwriting in place — mirrors the project's existing versioning pattern (`CommunicationVersion`/`CommunicationRevision`).
- **v1's exact feature list and weights are explicitly left as documented TBD** — not guessed now. The plan itself is "observe real filtered data first," so locking numbers today would defeat that plan's own premise.

---

## 2. Data pipeline architecture — Bronze → Silver → Gold

### 2.1 Physical layout

**One Postgres database, three schemas** (`bronze`, `silver`, `gold`) alongside the existing operational schema (`docs/entities.md`'s Company/Match/Communication model). No separate lake/warehouse — unjustified operational overhead at this volume (2 sources, low request rate), and nothing about this design forecloses moving to a real lake later if volume ever justifies it.

### 2.2 Bronze layer

- **Per-mechanism raw tables, not per-source.** Revised after comparing against `career-ops` (a different local project — see note below): rather than one table per individual source (`bronze.hn_raw`, `bronze.yc_raw`, ...), Bronze tables are grouped by ingestion mechanism — `bronze.api_ingest`, `bronze.web_scrape_ingest`, `bronze.newsletter_ingest`. Every one of Huginn's candidate sources maps to exactly one of these three: `api` (HN's Firebase API, YC's direct Algolia query, CORDIS, OpenCorporates), `web_scrape` (VC portfolio boards without an API, Ramp, Harmonic), `newsletter` (the four Substack-backed newsletters). More mechanisms can be added later if a genuinely different one shows up. Each table carries a `source` column (`hn`, `yc`, ...) to distinguish rows within it. This groups tooling and operational concerns (retry policy, schema-drift checks, freshness cadence defaults) by mechanism, which is the more natural grouping than by individual source — HN and a future CORDIS adapter behave alike operationally (poll on a schedule, expect JSON) even though their payloads look nothing alike.
- **Schema-on-read, unaffected by the collapse.** Bronze already stores the payload close to as-fetched with no field mapping or cleaning — collapsing sources into a shared table per mechanism just means the payload sits in a `payload JSONB` column, with each source's raw shape untouched inside it. Metadata columns: `source`, fetch timestamp, run ID, `last_checked_at` (see write behavior below — distinct from the fetch timestamp; it's updated on a hash-match "still unchanged" check, not on every fetch).
- **Uniqueness key becomes `(source, stable_id)`, not `stable_id` alone.** A direct consequence of sharing a table across sources: HN's and YC's native IDs could otherwise collide. This applies to both the write-behavior de-dup below and any future index/constraint on the table.
- **Content-hash computed at ingest time**, over a **deliberately chosen stable field subset per source** — not the full raw payload, using **SHA-256** (per `data-pipeline-standards.md`'s recommendation). This selection logic stays adapter-specific (each adapter knows which of its own fields matter) regardless of which shared table the resulting hash lands in. Rationale: sources have no reliable native cursor (YC's Algolia backend has no `updated_at`; HN Firebase items can be silently edited post-posting), so the hash is a self-generated substitute watermark: `(source, stable_id, content_hash)` replaces `(source, stable_id, updated_at)`. Hashing the *full* raw payload risks false "changed" signals from volatile noise fields (e.g. Algolia's internal rank/relevance score, `_highlightResult` metadata) that would defeat the whole point of using it as a stable watermark. The chosen fields are given light normalization (whitespace collapsing, casing) purely for the purposes of computing this hash, so that formatting-only differences don't register as false "changed" signals — this is not the same thing as Silver's cleaning/standardization step; the Bronze row itself is still stored as the raw, unmodified payload.
- **Write behavior:** if a fetch's hash matches the last stored hash for that `(source, stable_id)`, **do not insert a new row** — instead bump the `last_checked_at` timestamp on the existing row. This distinguishes "checked, confirmed unchanged" from "haven't successfully checked this in a while," which the freshness/zero-row alerting layer (see `data-pipeline-standards.md`) depends on to tell a healthy-but-static source apart from a silently-broken job.

*Note on the `career-ops` comparison:* that project (a separate local project, unrelated to Huginn) turned out not to have a bronze/raw-archival layer at all — it normalizes every source directly into one unified record at ingestion time, with no per-source raw storage to compare against. It did validate that Huginn's ports-and-adapters ingestion shape (one adapter per source, a shared contract) is a sound, independently-arrived-at pattern, and its `data/scan-history.tsv` file (an append-only log with columns added over time, older rows read positionally and tolerating their absence) is a real, if different, precedent for handling heterogeneous/evolving data — worth keeping in mind if Bronze's shape ever needs to evolve without a migration.

### 2.3 Silver layer

- **Role:** cleaning, standardization, **and cross-source entity resolution** (domain-as-canonical-key → normalize → strip legal suffixes → Jaro-Winkler + token-Jaccard fallback, per the prior session's locked entity-resolution recipe). This placement is **consistent with general medallion-architecture guidance**: Silver is commonly described as the place for deduplication/entity resolution/MDM-style merging, not a separate Silver→Gold boundary step (see References — this corrected an earlier draft assumption made mid-session, which had suggested resolution belonged between Silver and Gold). The supporting sources are explainer/blog-tier, not a canonical spec, so treat this as corroboration of a reasonable, common pattern rather than a settled, authoritative rule.
- **Structure:** per-source staging tables inside the Silver schema (e.g. `silver.hn_postings`, `silver.yc_listings` — each conformed to a common shape but not yet merged across sources), feeding a single cross-source **resolved-signals table** (`silver.resolved_signals`) — one row per original signal (a hiring post, a funding listing), still at event grain, with the raw company name replaced by the canonical company identifier entity resolution produced. This deliberately stays a single table, *not* pre-split into separate company and signal tables — verified against real medallion/dimensional-modeling practice (see `industry-references-elt-medallion.md`): the fact/dimension split belongs to Gold's dimensional model, not Silver's integration step. An earlier draft of this document briefly claimed otherwise mid-session before that was checked. Rationale for the per-source staging split specifically: keeps each source adapter's cleaning logic independently inspectable/debuggable, separate from cross-source resolution logic.
- **Grain:** current-state upsert only — no version history at Silver. Bronze already preserves full raw history for audit/replay; Silver doesn't need to re-solve that problem. **Caveat:** because entity-resolution merge decisions happen at Silver, this also means there's no recorded prior state at or below Silver to diagnose or roll back from if a merge is later found to be wrong — Gold's SCD Type 2 history (§2.4) is the earliest point a prior state becomes recoverable, and even that only captures Gold-level attributes, not the merge decision itself. This is an accepted MVP trade-off, not an oversight.

### 2.4 Gold layer

- **Role:** the dimensional model built from Silver's integrated data. A `Company` dimension (every company Silver has resolved and evaluated against the ICP filter at least once) and a `CompanySignal` fact table (one row per signal from `silver.resolved_signals`, for companies that made it into Gold), plus enrichment on the Company dimension (Team/About-page scraping, the hand-authored team-composition/soft-signal heuristic, per the prior session's Q4 decision that enrichment only runs on companies that already passed the cheap filters). This fact/dimension split is exactly where standard practice puts it, verified against Databricks and Kimball (`industry-references-elt-medallion.md`): dimensional modeling is Gold's job, not Silver's.
  - **Clarifying note on scope:** the `Company` dimension is not limited to companies currently passing the ICP filter. A company's row persists (with history, see below) regardless of its current pass or fail status. ICP-filter-pass is a tracked attribute on the row, not a gate on whether the row exists. Seeing "did this company only recently start passing the ICP filter" requires that a company which currently fails, or previously failed, still has a recoverable prior state to look back on.
  - Enrichment's placement in Gold is explicitly acknowledged as provisional. The user believes it may belong somewhere else architecturally, but is keeping it in Gold for now rather than resolving that placement question in this session.
- **History: current-plus-history split, not a single SCD Type 2 table (ADR-0002, revised 2026-09-05).** The original design versioned `Company` in place with `valid_from`/`valid_to`, an `is_current` flag, and a surrogate key that's new per version, per Kimball's canonical Type 2 definition (`industry-references-elt-medallion.md`). That design was correct per the standard, but wrong for Huginn's actual read pattern: every scoring read needs current state, and Type 2 makes that read depend on remembering an `is_current` filter every time. Missing it silently includes stale versions.
  - Revised design: `Company` holds exactly one row per company, always, overwritten in place when any field changes, including the Type 2 tracked fields. No `is_current` flag and no `valid_to` needed. There is nothing else in that table to filter out.
  - `CompanyHistory` gets a new row only when a Type 2 tracked field changes. The superseded values move there with a `valid_from`/`valid_to` window; the new values overwrite `Company` in place. This is the pattern Wikipedia's SCD article calls "Type 4 / history tables," distinct from Kimball Group's own Type 4 definition (a mini-dimension for volatile attributes). The naming is genuinely contested between sources; this document calls it the history-table pattern to avoid the collision.
  - The durable/natural key (domain) lives on `Company` and is denormalized onto `CompanyHistory` rows for convenience. `Company.Id` no longer needs to change per version, since only one row per company ever exists there.
- **Versioning trigger: hybrid Type 1 / Type 2 classification, unchanged by the above.** Each Gold column is still classified Type 1 (overwritten in `Company`, no history kept, e.g. cosmetic/descriptive fields) or Type 2 (a change writes the old value to `CompanyHistory` before overwriting `Company`, e.g. ICP-filter-pass status, sector classification, enrichment output). This directly avoids needing "intelligent"/semantic diffing to judge whether a wording change is meaningful; the column classification decides that up front. The cited SCD sources are tutorial/blog-tier corroboration of a real, widely-used pattern, not a canonical dimensional-modeling reference, cited as reasonable support, not proof of a single correct approach.
  - The principle is locked. The exact column-by-column classification is deferred to schema-writing time, once the concrete Gold schema is drafted (Jira KAN-20).

### 2.5 Matching step (downstream of Gold — separate from the ELT pipeline)

Explicitly **out of scope for this session** — flagged as needing "more intensive logic" than the ELT pipeline itself, not yet designed. Known responsibilities so far (not a full design):
- Consumes a Gold record and creates the operational `Match` row.
- Must check against previously-sent Matches to avoid resurfacing a company whose signal is still inside the recency window across multiple digest cycles.
- Needs to apply the user's current ICP/preference parameters (which may have been updated since a company was first evaluated) and possibly incorporate additional preference signals not yet specified.
- The user is deliberately not designing this further right now — parked for a future session.

---

## 3. References

**Internal (this project):**
- `Huginn/architecture-notes/data-pipeline-standards.md` — entity-resolution recipe, content-hash-as-watermark rationale, orchestration/observability recommendations.
- `Huginn/architecture-notes/industry-references-elt-medallion.md` — Databricks/Kimball/dbt/Fivetran primary sources checked against this document's design, point by point.
- `Huginn/adr/0002-gold-current-history-split.md` — the current-plus-history decision that revised Gold's SCD Type 2 design, superseding this document's original §2.4 grain description.
- `Huginn/docs/sources/*.md` — per-source access/shape findings (HN, YC, and 7 deferred sources).
- Memory: `huginn_mvp_scope_decisions.md`, `huginn_source_research.md`.
- Jira: KAN-8 (scoring/weighting design ticket, being updated to reflect the phasing decisions in §1).

**External (fetched live, 2026-09-05):** these are general explainer/blog-tier sources, cited as corroboration that a pattern is commonly used — not canonical specs, and not treated as settled-beyond-doubt verification of the design choices above.
- Medallion architecture / Silver-layer entity resolution placement:
  - [Medallion Architecture: Bronze, Silver and Gold Layers in Modern Lakehouses — Tacnode](https://tacnode.io/post/medallion-architecture)
  - [Revisiting Medallion Architecture — Data Engineering Weekly](https://www.dataengineeringweekly.com/p/revisiting-medallion-architecture) (note: a critical-reassessment piece, not a simple confirmation — read alongside the others rather than as standalone proof)
  - [Medallion Architecture: Bronze, Silver & Gold Layers Explained (2026 Guide) — Dataforest](https://dataforest.ai/blog/medallion-architecture)
- SCD Type 2 / hybrid Type 1+Type 2 column classification:
  - [How to Build Slowly Changing Dimensions — OneUptime](https://oneuptime.com/blog/post/2026-01-30-slowly-changing-dimensions/view)
  - [Master Slowly Changing Dimensions Type 2 — Analytics Engineering](https://www.analyticsengineering.com/resources/slowly-changing-dimensions-type-2-explained)
  - [Slowly Changing Dimensions (2026): SCD Types 1-6 Explained — DataDriven](https://datadriven.io/data-modeling/slowly-changing-dimensions)
