Status: DRAFT. Architecture decided across a series of design sessions, September 2026. No code written yet.
Author: Khaled Awashreh

Supersedes [Huginn Diagrams](https://kawashreh.atlassian.net/wiki/spaces/Huginn/pages/950273/Huginn+Diagrams) v1.3 wherever its "Not yet specified" table has since been resolved below. Its diagrams are the historical source for this document's graphs. This document is the authoritative, current-state architecture.

Companion documents: [Huginn Concept Doc](https://kawashreh.atlassian.net/wiki/spaces/Huginn/pages/917506/Huginn+Concept+Doc) (v1.3, product vision, on Confluence), `docs/entities.md` (domain schema, in progress), `architecture-notes/` (supporting research), `adr/` (decision records), Jira epic KAN-16 (tracked tech debt and research debt). Full list in section 13.

Architecture at a glance:

1. Storage: one Postgres database. Three ELT schemas (bronze, silver, gold) feed a separate operational schema.
2. Ingestion: ports and adapters, two sources at launch, HN "Who's Hiring" and the YC directory.
3. Entity resolution: runs at silver, domain-key first, Jaro-Winkler/token-Jaccard fallback.
4. Scoring: two stages. v0 ranks by recency alone. The weighted composite (v1) is deferred until there is real filtered-data volume to design against.
5. Delivery: a weekly email digest to a single user, on a data model that is multi-user from day one.
6. Out of scope this phase: everything above the domain layer (chatbot, dashboard, memory).

---

## 1. Problem and vision

1. Prospecting is the hardest part of running a solo services business, and often what stops people going independent at all: with no sales team it competes directly with billable work.
2. Startups are the high-fit case and the hard case at once. They lack the org charts, headcount plans, and formal recruiting processes that make bigger companies legible from outside, so the gap is visibility rather than fit, and the signal (funding, hiring, program milestones) is scattered and easy to miss on top of client work.
3. The answer is a Monday-morning email: a shortlist rather than a feed, pre-checked against criteria the user set, each entry carrying who the company is, why it surfaced, and a drafted outreach opener, learning over time what a "yes" and a "no" look like for this user.

Full problem statement and vision: [Huginn Concept Doc](https://kawashreh.atlassian.net/wiki/spaces/Huginn/pages/917506/Huginn+Concept+Doc) sections 1 and 2.

## 2. Goals and non-goals

Goals for this phase:

1. A weekly digest: a ranked shortlist of companies matching a plain-language ICP.
2. Per company: name, site, a LinkedIn search link (not scraped data), a short description, plain-language match reasoning, and a drafted outreach opener.
3. A domain model that's multi-user from day one, even though exactly one user exists right now. Phase 2 becomes additive, not a rebuild.
4. Ingestion from exactly two sources: HN "Who's Hiring" and the YC directory.

Non-goals for this phase:

1. No CRM or outreach automation. The opener is a draft to edit and send, not something the system sends on its own.
2. No chatbot UI and no conversational ICP refinement. ICP capture is a one-time plain-text-to-structured-filter form.
3. No scraped LinkedIn profile data. Search-link only. `hiQ v. LinkedIn` is the standing reason, and the same caution extends to person-level scraping generally (section 6).
4. No real-time alerts. Weekly batch by design.
5. No graph-traversal or ML model predicting a company's current needs. Team-composition signal, where it exists at all, is a hand-authored heuristic drawn only from company-owned pages and press releases.
6. No weighted composite score at launch. v0 ranks by recency alone (section 7).
7. No auth beyond a single hashed username and password. No role-based access control. No billing.

## 3. System overview

Five layers. The data pipeline feeds storage. Everything above it reads from storage.

```mermaid
flowchart TB
    SRC["Sources"]

    subgraph PIPE["Data pipeline"]
        direction LR
        ING["Ingestion"] --> TRN["Bronze to Silver to Gold"] --> POOL["Gold: shared pool"]
    end

    subgraph STORE["Storage: one Postgres database"]
        direction LR
        PG["bronze / silver / gold schemas<br/>+ operational schema"]
    end

    subgraph DOMAIN["Domain"]
        direction LR
        AUTH["Auth"] ~~~ CRUD["CRUD and business processes"] ~~~ SCORE["Matching and scoring"]
    end

    subgraph AGENT["Agentic workflow, deferred"]
        direction LR
        CHAT["Chatbot agent"] ~~~ DIGEST["Digest composition"]
    end

    subgraph PRES["Presentation, deferred"]
        direction LR
        MAIL["Email"] ~~~ DASH["Dashboard"]
    end

    USR["User"]

    SRC --> PIPE --> STORE --> DOMAIN --> AGENT --> PRES --> USR

    classDef deferred stroke-dasharray: 5 5
    class CHAT,DIGEST,MAIL,DASH deferred
```

Collection is shared infrastructure, matching is personal. The pipeline and the gold pool serve every user and are expensive to re-run, since sources rate-limit and some content becomes unavailable over time. Everything from the domain layer up is specific to one user and re-runnable at no cost.

Scoring lives in the domain layer, not the agentic layer: it is batch work, it must stay explainable per feature because the digest renders its reasoning, and both the digest and any future chatbot read its output rather than each other's.

## 4. Data pipeline: bronze, silver, gold

One Postgres database carries three schemas, `bronze`, `silver`, and `gold`, alongside the operational schema described in section 9. No separate lake or warehouse: unjustified overhead at two sources and low request volume, and nothing here forecloses moving to one later if volume justifies it.

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

    subgraph GOLD["gold schema: dimensional model"]
        GD["Company dimension<br/>current state only, one row per company"]
        GH["CompanyHistory<br/>written only when a tracked field changes"]
        GF["CompanySignal fact table"]
        GF --> GD
        GD -.->|"superseded values move here"| GH
    end

    MATCH["Matching step, deferred, KAN-18"]

    SRC --> BR --> SS
    SR --> GF
    GD -.-> MATCH

    classDef deferred stroke-dasharray: 5 5
    class MATCH deferred
```

The generic medallion, schema-on-read, dimensional-modelling, and SCD patterns behind these layers are not restated here. The primary sources are collected in `architecture-notes/industry-references-elt-medallion.md`. What follows is only where Huginn makes a choice.

### 4.1 Bronze

1. Tables group by ingestion mechanism, not by source: `bronze.api_ingest`, `bronze.web_scrape_ingest`, `bronze.newsletter_ingest`. HN and YC are both `api` today. The candidate sources in [Huginn Concept Doc](https://kawashreh.atlassian.net/wiki/spaces/Huginn/pages/917506/Huginn+Concept+Doc) section 7 map to `web_scrape` (VC boards, Ramp, Harmonic) or `newsletter` (the four Substack feeds) when added.
2. Columns: `payload` (close to as-fetched, no field mapping or cleaning), `source` (`hn`, `yc`, and so on), fetch timestamp, run ID, `last_checked_at`.
3. Watermarking is by content hash, because neither HN's Firebase API nor YC's Algolia backend offers a reliable changed-only cursor. A SHA-256 over a deliberately chosen, lightly normalized subset of each source's fields gives `(source, stable_id, content_hash)` where a native `updated_at` would sit. The `source` qualifier keeps two sources' native IDs from colliding in a shared table.
4. A fetch whose hash already exists writes nothing and bumps `last_checked_at` instead, which tells a healthy-but-static source apart from a job that has silently stopped running. A fetch whose hash differs overwrites the existing row in place: `UNIQUE (source, stable_id)` allows exactly one row per entity, so Bronze holds only the latest raw payload per entity, not every prior version.

### 4.2 Silver

1. Per-source staging tables, each conformed to a common shape but not merged across sources (ADR-0001), so HN's cleaning logic and YC's stay independently inspectable.
2. One cross-source `resolved_signals` table then runs entity resolution (section 6) at event grain, one row per original signal, raw company name replaced by a resolved canonical identifier.
3. No dimension/fact split at this layer. That is Gold's job, per Databricks and Kimball.
4. Current-state upsert only, no version history. Bronze does not preserve prior versions either, it holds only the latest raw payload per entity (section 4.1 point 4), so a wrong entity-resolution merge has no prior raw state anywhere in the pipeline to diagnose or roll back from. Accepted trade-off, revisit if it bites in practice.

### 4.3 Gold

A Kimball dimensional model over Silver's resolved signals: `Company` (dimension) and `CompanySignal` (fact), plus enrichment on the dimension (the team-composition/soft-signal heuristic, run only on companies that already passed the ICP filter).

`Company` covers every company Silver has resolved and evaluated against the filter at least once. ICP-filter-pass is a tracked attribute on the row, not a gate on whether the row exists, so a company that later stops passing keeps its record.

History is a current-plus-history split rather than a single SCD Type 2 table (ADR-0002):

1. `Company`: exactly one row per company, always, overwritten in place whenever any field changes.
2. `CompanyHistory`: a new row only when a Type 2 tracked field changes (`BusinessSector`, `TeamCompositionSignal`, `IcpFilterPass`), holding the superseded values with a `ValidFrom`/`ValidTo` window.
3. Type 1 cosmetic fields: overwrite in `Company`, no history.

The reason for the split: every scoring read needs current state, and a single Type 2 table makes that read depend on remembering an `IsCurrent` filter every time. `Company` cannot return a stale row.

Column-by-column Type 1 / Type 2 classification is pending the concrete schema (Jira KAN-20). Enrichment's placement in Gold is provisional and may move in a later architecture pass.

### 4.4 Matching

Matching, the step that turns a Gold row into an operational `Match`, is explicitly out of scope for this document. It needs to check a company against previously sent matches, so a signal still inside its recency window does not resurface week after week, and reapply the user's current ICP and preferences. Deferred and tracked as Jira KAN-18.

## 5. Ingestion

A ports-and-adapters arrangement.

```mermaid
flowchart TB
    SCH["Scheduler: cron + job_runs table"]

    subgraph CORE["Core"]
        ISVC["IngestionService"]
    end

    subgraph PORT["Ports"]
        PS["SourcePort"]
        PR["RawStorePort"]
        PT["StatePort: per-entity content hash"]
    end

    subgraph IN["Adapters, Phase 0"]
        A1["HN: official Firebase API"]
        A2["YC: direct Algolia search-key query"]
    end

    SCH --> ISVC
    ISVC ==>|"Defines and calls"| PORT
    PS --> A1
    PS --> A2
    PR --> BR["Bronze"]
    PT --> CUR["Hash map per stable ID"]
```

`IngestionService` holds the logic that would otherwise be reimplemented per adapter: which sources to fetch, in what order, and when a run counts as complete. Each adapter owns a single protocol and holds no ingestion policy of its own.

Both Phase 0 sources are API-shaped, not scraped HTML. HN's official Firebase API needs no auth and has no rate limit. YC's directory has no official API but exposes a public, search-only Algolia key in its frontend, which the adapter queries directly rather than parsing rendered pages. `StatePort` holds the content-hash map from section 4 in place of a source-provided cursor.

Orchestration is cron plus a `job_runs` table, the confirmed default at this scale. Prefect (self-hosted OSS) and GitHub Actions `schedule:` triggers are named upgrade paths, neither adopted now (Jira KAN-9).

One risk is carried forward unresolved rather than quietly assumed: YC's Terms of Service explicitly prohibit scraping and data-mining, while its `robots.txt` says nothing about querying the Algolia backend directly. YC is locked as a Phase 0 source, but the legal exposure underneath that choice has not been closed out (Jira KAN-7).

## 6. Entity resolution

Domain is the canonical key first. A company's registrable domain, normalized (lowercase, no `www.`, no protocol or trailing slash), is cheap and nearly unambiguous.

Where no domain match exists, the fallback is:

1. Normalize the name and strip legal suffixes (Inc., LLC, Ltd.), using OpenSanctions' suffix list rather than a hand-rolled one.
2. Score with Jaro-Winkler for character-level similarity plus token-Jaccard for word-order variance ("Acme Robotics" vs "Robotics Acme Inc").
3. Act on the Jaro-Winkler score: 0.92 and above auto-matches, 0.85 to 0.92 goes to a manual-review queue rather than an automatic decision, below 0.85 is treated as no match.

Full probabilistic record linkage (Splink, `dedupe`, Zingg) is deliberately deferred. That machinery earns its cost at a scale this system does not have: no training pairs, no meaningful class imbalance, and no throughput problem to justify it. The trigger to revisit it is a real, sizeable backlog in the manual-review queue.

This recipe was researched and adopted without the author's own background in entity resolution. Accepted as debt, tracked at Jira KAN-4, to be properly learned once that manual-review backlog exists.

## 7. Digest and scoring

Composite scoring ships in two stages, not one shot:

1. v0 ranks by recency alone, freshest qualifying signal first, among companies that already passed the ICP filter. With no `MatchFeedback` history to check them against, inventing feature weights now would be guessing, where recency is free and defensible. v0 is a shippable product, not a spike: it sends real digests and generates the usage data v1 needs. The user sees the plain underlying signal, "posted 2 days ago" or "raised a Series A 11 days ago," never a manufactured score.
2. v1 adds a weighted composite once v0 has produced enough filtered-data volume to design weights against. Its inputs (stage, sector, funding recency, source quality, the team-composition signal) and how they combine are left deliberately open (Jira KAN-8), since locking numbers now defeats the point of waiting. The user then sees a qualitative tier ("Strong / Good / Fair match"), not a raw number, which would claim a precision the weights will not have.

A `Match`'s score snapshots at creation and freezes permanently once it is `Sent`: a sent digest is what the user actually saw, and any future feedback analysis needs to compare against that, not a version revised in hindsight. A still-pending `Match` can be recomputed, triggered by late-arriving enrichment data or by a global weight retune once feedback exists. Each recompute is versioned rather than overwritten in place, mirroring the versioning already present elsewhere in the schema (`CommunicationVersion`, `CommunicationRevision`).

The feedback loop itself, a positive or negative rating on `MatchFeedback` adjusting future weights, is schema-ready but not wired to anything yet.

## 8. Agentic workflow, retrieval, presentation: deferred

Out of scope for this phase and deliberately abstract pending a decision later. Carried forward for continuity:

1. A chatbot agent and digest composition would sit on a shared harness: an explicit, named tool contract, plus the model routing in section 10. Two experimental memory side-channels, MuninnDB and Letta, are named as candidates for soft context only, and the system has to keep working with both absent.
2. Retrieval, if a chatbot ships, would narrow with a structured filter before re-ranking by vector similarity, on the `pgvector` storage in section 10.
3. Presentation is a weekly email digest for now. Dashboard scope is undecided; with one user, the realistic version is a simple page alongside email, not a full application.

## 9. Data model

`docs/entities.md` holds the schema in progress and is the source for the diagram below, which shows identifying fields only. Its "Gold" heading predates this document's pipeline layering and mixes two things this document separates: the ELT Gold layer (section 4), which is `Company`, `CompanyHistory`, and `CompanySignal`, and the operational schema below them, written by the matching step (sections 4, 7) rather than by the ELT pipeline.

```mermaid
erDiagram
    User ||--o{ Match : "receives"
    Company ||--o{ Match : "shared pool, matched per user"
    Company ||--o{ CompanySignal : "emits"
    Company ||--o{ CompanyHistory : "superseded values move to"
    Company ||--o{ Employee : "employs"
    Match ||--o| MatchScore : "scored by"
    Match ||--o{ MatchFeedback : "rated by"
    Match ||--o{ Activity : "notes and follow-ups"
    Match ||--o{ Communication : "outreach draft"
    Employee |o--o{ Activity : "optionally about"
    Communication ||--o{ CommunicationVersion : "versioned as"
    CommunicationVersion ||--o{ CommunicationRevision : "revised by"
    CommunicationRevision ||--o{ CommunicationTurn : "composed of"

    User {
        GUID Id PK
        StructuredFilter icp_profile "from the section 2 ICP form"
    }
    Company {
        GUID Id PK
        String Domain "resolved natural key, section 6"
        String BusinessSector "Type 2 tracked"
        Enum TeamCompositionSignal "Type 2 tracked"
        Boolean IcpFilterPass "Type 2 tracked, attribute not a gate"
    }
    CompanyHistory {
        GUID Id PK
        GUID CompanyId FK
        DateTimeOffset ValidFrom
        DateTimeOffset ValidTo "row written only on a Type 2 change, ADR-0002"
    }
    CompanySignal {
        GUID Id PK
        GUID CompanyId FK
        Enum SignalType "Funding, Hiring, ProgramMilestone, and so on"
        String Source
        DateTimeOffset OccurredOn
    }
    Employee {
        GUID Id PK
        GUID CompanyId FK "person-level, sourced only per section 2 non-goals"
    }
    Match {
        GUID Id PK
        GUID UserId FK "one row per user x company"
        GUID CompanyId FK
        Enum Status
    }
    MatchScore {
        GUID Id PK
        GUID MatchId FK
        Enum ScoringAlgorithm
        Integer Score
        JSON FeatureBreakdown "per-feature breakdown"
    }
    MatchFeedback {
        GUID Id PK
        GUID MatchId FK
        Enum Rating "Positive, Negative"
    }
    Activity {
        GUID Id PK
        GUID MatchId FK
        GUID EmployeeId FK "nullable"
        Enum Type
    }
    Communication {
        GUID Id PK
        GUID MatchId FK
        Enum Channel
        Enum Status
    }
    CommunicationVersion {
        GUID Id PK
        GUID CommunicationId FK
        Integer VersionNumber
    }
    CommunicationRevision {
        GUID Id PK
        GUID CommunicationVersionId FK
        Enum AgentType "User, AI"
    }
    CommunicationTurn {
        GUID Id PK
        GUID CommunicationRevisionId FK
        Enum Role "User, Assistant"
    }
```

`MatchScore` as currently sketched is a single row per match. Section 7's recompute design will need it to grow into a versioned history before v1 scoring ships.

## 10. Cross-cutting concerns

| Concern | Decision |
|---|---|
| Secrets | Behind an abstracted provider. Local key vault now, remote later. |
| Configuration | YAML. Framework not yet chosen. |
| Deployment | Local for now, containerized later. |
| Vector storage | `pgvector` on Postgres, no separate infrastructure, if retrieval ships. |
| Model cost | Small models for background work, the larger model reserved for user-facing chat, if it ships. |

These carry forward unrevisited from the original diagram set.

## 11. Open items

| Item | Area | Tracking |
|---|---|---|
| v1 scoring: feature list and weights | Domain | KAN-8 |
| Matching-step logic: resurfacing check, ICP/preference reapplication | Domain | KAN-18 |
| Gold Type 1 / Type 2 column classification, concretely | Data pipeline | KAN-20 |
| YC ToS-vs-robots.txt legal exposure | Ingestion | KAN-7 |
| Team-composition inference method, concretely | Data pipeline | not tracked |
| ICP capture flow, concretely (the one-time form) | Domain | not tracked |
| Enrichment's long-term home (currently Gold, provisional) | Data pipeline | not tracked |
| Contents of the agentic workflow layer | Agentic | not tracked |
| Shared or separate embedding spaces | Retrieval | not tracked |
| Whether digest and any future notifications share one delivery mechanism | Presentation | not tracked |
| Dashboard scope | Presentation | not tracked |
| Concrete table columns and types | Data model | not tracked |
| A formal constraint against person-level fields sourced from third parties | Data model | not tracked |
| Testing approach for normalization and entity resolution | Cross-cutting | not tracked |
| Logging and error visibility as one story | Cross-cutting | not tracked |

Resolved since the original diagram set, kept for continuity: first two sources (HN, YC), entity resolution strategy (section 6), orchestration mechanism (cron plus `job_runs`), and the v0 half of the scoring mechanism (section 7).

## 12. Tracked debt and research

Jira epic KAN-16 holds tech debt (tools and libraries chosen without deep review, for example the entity-resolution recipe in section 6) and research debt (patterns and conventions worth learning properly, for example the SCD taxonomy behind section 4's Gold layer). Decisions with a settled rationale live in this document; open gaps live in Jira.

## 13. References

1. [Huginn Concept Doc](https://kawashreh.atlassian.net/wiki/spaces/Huginn/pages/917506/Huginn+Concept+Doc) (Confluence): product vision and phased approach.
2. [Huginn Diagrams](https://kawashreh.atlassian.net/wiki/spaces/Huginn/pages/950273/Huginn+Diagrams) (Confluence): original diagram set this document supersedes where resolved.
3. `docs/entities.md`: domain schema in progress.
4. `architecture-notes/data-pipeline-standards.md`: entity resolution, watermarking, orchestration, and observability research.
5. `architecture-notes/elt-pipeline-and-scoring-decisions.md`: the pipeline and scoring design session behind sections 4 and 7.
6. `architecture-notes/industry-references-elt-medallion.md`: Databricks, Kimball, dbt, and Fivetran primary sources this document's pipeline design is checked against.
7. `docs/sources/*.md`: per-source access and risk findings.
8. Jira epic KAN-16: tracked tech debt and research debt.
9. `adr/0001-per-source-silver-staging-tables.md` and `adr/0002-gold-current-history-split.md`: decision records for the Silver and Gold layer designs above.
