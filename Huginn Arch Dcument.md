Status: DRAFT — architecture decided across a series of design sessions, September 2026. No code written yet.
Author: Khaled Awashreh
Supersedes: `huginn-diagrams.md` v1.3's "Not yet specified" table wherever an item below has since been resolved. The diagrams there are the historical source for this document's graphs; this document is now the authoritative, current-state architecture.
Companion documents: `huginn-concept-doc.md` (v1.3, product vision), `Entites.md` (domain schema, in progress), `architecture-notes/data-pipeline-standards.md` and `architecture-notes/elt-pipeline-and-scoring-decisions.md` (supporting research), Jira epic KAN-16 (tracked tech debt and research debt).

**Architecture at a glance:** a single Postgres database carries the system — three ELT schemas (bronze, silver, gold) feeding a separate operational schema. Ingestion follows a ports-and-adapters shape with two sources at launch, Hacker News "Who's Hiring" and the YC directory. Entity resolution runs at silver, domain-key first with a Jaro-Winkler/token-Jaccard fallback. Scoring ships in two stages: v0 ranks by recency alone, and a weighted composite (v1) is deferred until there's real filtered-data volume to design against. Delivery is a weekly email digest to a single user for now, though the data model is multi-user from day one. Everything above the domain layer — chatbot, dashboard, memory — is explicitly out of scope for this phase.

---

## 1. Problem and vision

Finding leads is one of the hardest parts of running a services business — often the hurdle that stops people from going independent at all. No sales team means prospecting competes directly with billable work.

Startups make it worse. They lack the org charts, headcount plans, and formal recruiting processes that make bigger companies legible from the outside. But that same scrappiness is the opportunity: fast, informal, no-procurement-cycle startups are exactly what solo providers are built to serve. The gap isn't fit — it's visibility. The signal exists (funding, hiring, program milestones); it's just scattered and easy to miss on top of client work.

Monday morning, an email is already waiting: a handful of companies that could be meaningful leads, right now. Not a feed to monitor — a short shortlist, already checked against criteria the user set themselves.

Each entry gives enough to know quickly if it's worth a message: who they are, why they surfaced, and a starting line for outreach. Reaching out becomes a Monday habit instead of a task that keeps getting pushed to later.

Over time the list gets better — it learns what a "yes" and "no" actually look like for this person. The hardest part of running a services business, finding who needs you, happens in the background, and the result is waiting every Monday.

## 2. Goals and non-goals

**Goals for this phase:**

- A weekly digest — a ranked shortlist of companies matching a plain-language ICP.
- Per company: name, site, a LinkedIn search link (not scraped data), a short description, plain-language match reasoning, and a drafted outreach opener.
- A domain model that's multi-user from day one, even though exactly one user exists right now — Phase 2 becomes additive, not a rebuild.
- Ingestion from exactly two sources: HN "Who's Hiring" and the YC directory.

**Non-goals for this phase:**

- No CRM or outreach automation. The opener is a draft to edit and send, not something the system sends on its own.
- No chatbot UI and no conversational ICP refinement. ICP capture is a one-time plain-text-to-structured-filter form.
- No scraped LinkedIn profile data — search-link only. `hiQ v. LinkedIn` is the standing reason; the same caution extends to person-level scraping generally (§6).
- No real-time alerts. Weekly batch by design.
- No graph-traversal or ML model predicting a company's current needs. Team-composition signal, where it exists at all, is a hand-authored heuristic drawn only from company-owned pages and press releases.
- No weighted composite score at launch. v0 ranks by recency alone (§7).
- No auth beyond a single hashed username and password, no role-based access control, no billing.

## 3. System overview

Five layers. The data pipeline feeds storage; everything above it reads from storage.

```mermaid
flowchart TB
    SRC["Sources"]

    subgraph PIPE["Data pipeline"]
        direction LR
        ING["Ingestion"] --> TRN["Bronze to Silver to Gold"] --> POOL["Gold: shared pool"]
    end

    subgraph STORE["Storage — one Postgres database"]
        direction LR
        PG["bronze / silver / gold schemas<br/>+ operational schema"]
    end

    subgraph DOMAIN["Domain"]
        direction LR
        AUTH["Auth"] ~~~ CRUD["CRUD and business processes"] ~~~ SCORE["Matching and scoring"]
    end

    subgraph AGENT["Agentic workflow — deferred"]
        direction LR
        CHAT["Chatbot agent"] ~~~ DIGEST["Digest composition"]
    end

    subgraph PRES["Presentation — deferred"]
        direction LR
        MAIL["Email"] ~~~ DASH["Dashboard"]
    end

    USR["User"]

    SRC --> PIPE --> STORE --> DOMAIN --> AGENT --> PRES --> USR

    classDef deferred stroke-dasharray: 5 5
    class CHAT,DIGEST,MAIL,DASH deferred
```

Collection is shared infrastructure; matching is personal. The pipeline and the gold pool serve every user and are expensive to re-run, since sources rate-limit and some content becomes unavailable over time. Everything from the domain layer up is specific to a single user and can be re-run at no cost.

Scoring lives in the domain layer, not the agentic layer: it's batch work, it must stay explainable per feature since the digest renders its reasoning, and both the digest and any future chatbot read its output rather than each other's.

## 4. Data pipeline — bronze, silver, gold

One Postgres database carries three schemas — `bronze`, `silver`, `gold` — alongside the operational schema described in §9. No separate lake or warehouse: unjustified overhead at two sources and low request volume, and nothing here forecloses moving to one later if volume justifies it.

```mermaid
flowchart TB
    SRC["HN, YC"]

    subgraph BRONZE["bronze schema"]
        BR["Per-mechanism raw tables<br/>api_ingest / web_scrape_ingest / newsletter_ingest<br/>schema-on-read · source column · SHA-256 content hash"]
    end

    subgraph SILVER["silver schema"]
        SS["Per-source staging tables<br/>cleaned, conformed, not yet merged"]
        SR["resolved_signals table<br/>cross-source entity resolution, event grain<br/>current-state upsert, no version history"]
        SS --> SR
    end

    subgraph GOLD["gold schema — dimensional model"]
        GD["Company dimension<br/>ICP-filter status + enrichment<br/>SCD Type 2, surrogate key, is_current flag"]
        GF["CompanySignal fact table"]
        GF --> GD
    end

    MATCH["Matching step — deferred, KAN-18"]

    SRC --> BR --> SS
    SR --> GF
    GD -.-> MATCH

    classDef deferred stroke-dasharray: 5 5
    class MATCH deferred
```

**Bronze.** Tables are grouped by ingestion mechanism, not by individual source: `bronze.api_ingest`, `bronze.web_scrape_ingest`, `bronze.newsletter_ingest`. HN and YC are both `api` today; the other candidate sources catalogued in `huginn-concept-doc.md` §7 fall into `web_scrape` (VC boards, Ramp, Harmonic) or `newsletter` (the four Substack feeds) when they're eventually added. A `source` column (`hn`, `yc`, ...) distinguishes rows within a table. Each table holds the payload close to as-fetched in a `payload` column, with no field mapping or cleaning — Bronze stays schema-on-read regardless of how many sources share a table. Metadata: `source`, fetch timestamp, run ID, and `last_checked_at`. Neither HN's Firebase API nor YC's Algolia backend offers a reliable "give me only what changed" cursor, so a SHA-256 hash over a deliberately chosen, lightly normalized subset of each source's fields stands in for one: `(source, stable_id, content_hash)` where a native `updated_at` would otherwise sit — the `source` qualifier matters once multiple sources share a table, so two sources' native IDs can't collide. If a fetch's hash matches what's already stored, nothing new is written — `last_checked_at` is bumped on the existing row instead, so a healthy-but-static source can be told apart from a job that's silently stopped running.

**Silver.** Per-source staging tables conform each source to a common shape without merging across sources — HN's cleaning logic and YC's stay independently inspectable. A single cross-source `resolved_signals` table then runs entity resolution (§6) — still at event grain, one row per original signal, with the raw company name replaced by a resolved canonical identifier. This deliberately stops short of splitting into separate company and signal tables: verified against Databricks and Kimball (`architecture-notes/industry-references-elt-medallion.md`), that dimensional split is standard Gold work, not Silver's. Silver is current-state upsert only; Bronze already preserves full raw history, and Silver doesn't re-solve that problem. One accepted trade-off: if an entity-resolution merge later turns out wrong, there's no recorded prior state at or below Silver to diagnose or roll back from.

**Gold.** A dimensional model built from Silver's resolved signals: a `Company` dimension (every company Silver has resolved and evaluated against the ICP filter — stage, sector, recency — at least once) and a `CompanySignal` fact table, plus enrichment on the dimension — the team-composition/soft-signal heuristic, run only on companies that already passed the filter. ICP-filter-pass is itself a tracked attribute on the dimension, not a gate on whether the row exists — a company that later stops passing keeps its history rather than disappearing. The `Company` dimension is versioned as SCD Type 2 — `valid_from`/`valid_to`, an explicit `is_current` flag, and a surrogate key that's new per version while the durable key (domain) stays stable — using a hybrid Type 1/Type 2 column classification: cosmetic fields overwrite in place, while filter status, stage/sector classification, funding-recency bucket, and enrichment output each trigger a new version. The exact column-by-column split is pending the concrete schema (Jira KAN-20). Enrichment's placement in Gold is provisional — it may move in a later architecture pass.

**Matching**, the step that turns a Gold row into an operational `Match`, is explicitly out of scope for this document. It needs to check a company against previously sent matches (so a signal still inside its recency window doesn't resurface week after week) and reapply the user's current ICP and preferences. Deferred and tracked as Jira KAN-18.

## 5. Ingestion

A ports-and-adapters arrangement. The core defines the interfaces; adapters implement them.

```mermaid
flowchart TB
    SCH["Scheduler — cron + job_runs table"]

    subgraph CORE["Core"]
        ISVC["IngestionService"]
    end

    subgraph PORT["Ports"]
        PS["SourcePort"]
        PR["RawStorePort"]
        PT["StatePort — per-entity content hash"]
    end

    subgraph IN["Adapters, Phase 0"]
        A1["HN — official Firebase API"]
        A2["YC — direct Algolia search-key query"]
    end

    SCH --> ISVC
    ISVC ==>|"Defines and calls"| PORT
    PS --> A1
    PS --> A2
    PR --> BR["Bronze"]
    PT --> CUR["Hash map per stable ID"]
```

`IngestionService` holds the logic that would otherwise be reimplemented per adapter: which sources to fetch, in what order, and when a run counts as complete. Each adapter owns a single protocol and holds no ingestion policy of its own — adding a source means writing one adapter, not touching the core.

Both Phase 0 sources are API-shaped, not scraped HTML: HN's official Firebase API needs no auth and has no rate limit; YC's directory has no official API but exposes a public, search-only Algolia key in its frontend, which the adapter queries directly rather than parsing rendered pages. `StatePort` holds the content-hash map from §4 in place of a source-provided cursor.

Orchestration is cron plus a `job_runs` table — the confirmed default at this scale. Prefect (self-hosted OSS) and GitHub Actions `schedule:` triggers are named upgrade paths if that ever stops being enough; neither is adopted now (Jira KAN-9).

One risk is carried forward unresolved rather than quietly assumed: YC's Terms of Service explicitly prohibit scraping and data-mining, while its `robots.txt` says nothing about querying the Algolia backend directly. YC is locked as a Phase 0 source, but the legal exposure underneath that choice hasn't been closed out (Jira KAN-7).

## 6. Entity resolution

Domain is the canonical key first — a company's registrable domain, normalized (lowercase, no `www.`, no protocol or trailing slash), is cheap and nearly unambiguous. Where no domain match exists, the fallback is: normalize the name, strip legal suffixes (Inc., LLC, Ltd., using OpenSanctions' suffix list rather than a hand-rolled one), then Jaro-Winkler for character-level similarity plus token-Jaccard for word-order variance ("Acme Robotics" vs. "Robotics Acme Inc"). Jaro-Winkler ≥ 0.92 auto-matches; 0.85–0.92 goes to a manual-review queue rather than an automatic decision; below 0.85 is treated as no match.

Full probabilistic record linkage — Splink, `dedupe`, Zingg — is deliberately deferred. That machinery earns its cost at a scale this system doesn't have: no training pairs, no meaningful class imbalance, and no throughput problem to justify it. The trigger to revisit it is a real, sizeable backlog in the manual-review queue.

This recipe was researched and adopted without the author's own background in entity resolution — accepted as debt, tracked at Jira KAN-4, to be properly learned once that manual-review backlog exists.

## 7. Digest and scoring

Composite scoring ships in two stages rather than one shot.

**v0** ranks by recency alone — the freshest qualifying signal first — among companies that already passed the ICP filter. Inventing feature weights today, with no `MatchFeedback` history to check them against, would be guessing; recency ranking is free and produces a defensible order without guessing anything. v0 is a real, shippable product, not a spike: it sends actual digests and starts generating the usage data v1 will eventually need. What the user sees is the plain underlying signal — "posted 2 days ago," "raised a Series A 11 days ago" — never a manufactured score.

**v1** adds a real weighted composite once v0 has produced enough filtered-data volume to design feature weights against. What feeds it — stage, sector, funding recency, source quality, the team-composition signal — and how those combine is left deliberately open (Jira KAN-8); locking numbers now would defeat the point of waiting for real data first. When it ships, the user sees a qualitative tier ("Strong / Good / Fair match"), not a raw number — a bare score would claim a precision the weights won't actually have.

A `Match`'s score snapshots at creation and freezes permanently once it's `Sent` — a sent digest is what the user actually saw, and any future feedback analysis needs to compare against that, not a version revised in hindsight. A still-pending `Match` can be recomputed, triggered by late-arriving enrichment data or by a global weight retune once feedback exists; each recompute is versioned rather than overwritten in place, mirroring the versioning already present elsewhere in the schema (`CommunicationVersion`, `CommunicationRevision`).

The feedback loop itself — a 👍/👎 on `MatchFeedback` adjusting future weights — is schema-ready but not wired to anything yet.

## 8. Agentic workflow, retrieval, presentation — deferred

Everything past the domain layer is out of scope for this phase and deliberately abstract pending a decision later. Carried forward for continuity:

A chatbot agent and digest composition would sit on a shared harness (an explicit, named tool contract; model routing that reserves the larger model for user-facing chat and uses smaller models for background extraction). Two experimental memory side-channels, MuninnDB and Letta, are named as candidates for soft context only — nothing load-bearing would read from either, and the system has to keep working with both absent.

Retrieval, if a chatbot ships, would narrow with a structured filter before re-ranking by vector similarity in Postgres via `pgvector` rather than separate infrastructure — structured filtering can't rank by resemblance, and vector search alone doesn't keep the context small.

Presentation is a weekly email digest for now. A dashboard's scope is undecided — with one user, the realistic version is a simple page alongside email, not a full application.

## 9. Data model

`Entites.md` sketches the schema in progress. Its "Gold" heading predates this document's precise pipeline layering and mixes two things this document now separates: the ELT Gold layer (§4) and the operational schema that the matching step (§4, §7) writes to downstream of it.

**Gold ELT layer**, a dimension/fact pair (§4): `Company` (the dimension — resolved, filtered, enriched record, including `TeamCompositionSignal`, SCD Type 2 versioned) and `CompanySignal` (the fact table — the individual hiring, funding, or milestone events that fed a match, one row per signal with its source and occurrence date).

**Operational schema**, written by the matching step, not by the ELT pipeline: `Match` (one row per user × company, with status), `MatchScore` (score, scoring algorithm, per-feature breakdown as JSON), `MatchFeedback` (👍/👎), `Employee` (person-level data, sourced only per §2's non-goals), `Activity` (notes and follow-ups against a match), and `Communication`/`CommunicationVersion`/`CommunicationRevision`/`CommunicationTurn` (the outreach draft and its edit history). `MatchScore` as currently sketched is a single row per match; §7's recompute design will need it to grow into a versioned history before v1 scoring ships.

```mermaid
flowchart LR
    U["users<br/>icp_profile"]
    C["Gold: companies<br/>shared pool"]
    S["CompanySignal<br/>hiring, funding, milestones"]
    M["Match<br/>one row per user × company<br/>score, status"]

    U --> M
    C --> M
    C --> S
```

Ingestion and scoring stay decoupled from who's using the system, so a second user in a later phase is additive, not a rebuild.

## 10. Cross-cutting concerns

| Concern | Decision |
|---|---|
| Secrets | Behind an abstracted provider — local key vault now, remote later |
| Configuration | YAML; framework not yet chosen |
| Deployment | Local for now, containerized later |
| Vector storage | `pgvector` on Postgres, no separate infrastructure, if retrieval ships |
| Model cost | Small models for background work, the larger model reserved for user-facing chat, if it ships |

These carry forward from the original diagram set unrevisited — none of this session's work touched them.

## 11. Open items

| Item | Area | Tracking |
|---|---|---|
| v1 scoring: feature list and weights | Domain | KAN-8 |
| Matching-step logic: resurfacing check, ICP/preference reapplication | Domain | KAN-18 |
| Gold Type 1 / Type 2 column classification, concretely | Data pipeline | KAN-20 |
| YC ToS-vs-robots.txt legal exposure | Ingestion | KAN-7 |
| Team-composition inference method, concretely | Data pipeline | — |
| ICP capture flow, concretely (the one-time form) | Domain | — |
| Enrichment's long-term home (currently Gold, provisional) | Data pipeline | — |
| Contents of the agentic workflow layer | Agentic | — |
| Shared or separate embedding spaces | Retrieval | — |
| Whether digest and any future notifications share one delivery mechanism | Presentation | — |
| Dashboard scope | Presentation | — |
| Concrete table columns and types | Data model | — |
| A formal constraint against person-level fields sourced from third parties | Data model | — |
| Testing approach for normalization and entity resolution | Cross-cutting | — |
| Logging and error visibility as one story | Cross-cutting | — |

Resolved since the original diagram set — kept here for continuity, no longer open: first two sources (HN, YC), entity resolution strategy (§6), orchestration mechanism (cron + `job_runs`), and the v0 half of the scoring mechanism (§7).

## 12. Tracked debt and research

Jira epic KAN-16 holds what doesn't belong in this document: tech debt (tools and libraries chosen without deep review — e.g. the entity-resolution recipe in §6) and research debt (patterns and conventions worth learning properly — e.g. the SCD taxonomy behind §4's Gold layer). Decisions with a settled rationale live here, in this document; open gaps live in Jira.

## 13. References

- `huginn-concept-doc.md` — product vision and phased approach
- `huginn-diagrams.md` — original diagram set this document supersedes where resolved
- `Entites.md` — domain schema in progress
- `architecture-notes/data-pipeline-standards.md` — entity resolution, watermarking, orchestration, and observability research
- `architecture-notes/elt-pipeline-and-scoring-decisions.md` — the pipeline and scoring design session behind §4 and §7
- `architecture-notes/industry-references-elt-medallion.md` — Databricks/Kimball/dbt/Fivetran primary sources this document's pipeline design is checked against
- `sources/*.md` — per-source access and risk findings
- Jira epic KAN-16 — tracked tech debt and research debt
