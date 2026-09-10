# Huginn ELT Build Plan (KAN-21)

Breakdown of Jira epic KAN-21 into stories, tasks, and the research/design artifact each implementation task consumes before it starts. Covers Ingestion, Bronze, Silver, and Gold only, per the epic's own scope. Scoring, matching, and the agentic/presentation layers are explicitly out.

## 1. Ingestion (KAN-22)

Research already done, not part of this epic:

1. `docs/sources/hn-who-is-hiring.md`: HN Firebase API access, response shape, freshness, and open risks. Verified live 2026-09-05.
2. `docs/sources/yc-directory.md`: YC Algolia access pattern, response shape, ToS risk. Verified live 2026-09-05.

Design tasks (each produces the artifact its build task consumes):

1. KAN-37, port contracts. Artifact: interface-contract note for ApiSourcePort, WebScrapeSourcePort, NewsletterSourcePort. Blocks KAN-26.
2. KAN-38, HN fetch plan. Artifact: fetch-plan note translating `docs/sources/hn-who-is-hiring.md` into concrete choices (thread-discovery method, dead-item handling, RawRecord field mapping). Blocks KAN-29.
3. KAN-39, YC fetch plan. Artifact: fetch-plan note translating `docs/sources/yc-directory.md` into concrete choices (direct Algolia call vs the yc-oss/api mirror, query parameters, RawRecord field mapping). Blocks KAN-30.

Build tasks:

1. KAN-26, mechanism-specific SourcePort split. Consumes KAN-37's artifact.
2. KAN-29, HN adapter `fetch()`. Consumes KAN-38's artifact.
3. KAN-30, YC adapter `fetch()`. Consumes KAN-39's artifact. Legal exposure (KAN-7) stays open regardless of which access path is chosen.
4. KAN-27, job_runs table. New `ops` schema, an engineering call made now, not an architectural one.
5. KAN-28, IngestionService error isolation and job_runs wiring. Consumes KAN-27.
6. KAN-31, CLI entrypoint and cron scheduling.

Gap carried forward: KAN-7 (YC ToS vs robots.txt) stays open. The adapter is built anyway per explicit decision; building it does not resolve the legal question.

Integration artifact handed to Bronze: a working RawRecord stream from at least one adapter (HN, since it carries no legal blocker), shaped to the port contract from KAN-37.

## 2. Bronze (KAN-23)

Already done: schema (`db/schema/bronze.sql`), content-hash watermarking logic (`src/huginn/bronze/watermark.py`, tested).

Build tasks:

1. KAN-32, Postgres-backed RawStorePort. Consumes the RawRecord stream from Ingestion and `compute_content_hash`.
2. KAN-33, Postgres-backed StatePort. Consumes the same table access as KAN-32.

No design task needed here. The schema and hashing algorithm are already settled (ADR-0001, architecture document section 4.1); this story is wiring, not decision-making.

Integration artifact handed to Silver: real rows in `bronze.api_ingest`, from at least one source, with `content_hash` populated correctly.

## 3. Silver (KAN-24)

Scope decision for this epic: domain-key matching only. The fuzzy-match fallback stays research debt (KAN-4) and is not built here.

Build tasks:

1. KAN-34, per-source staging loaders (HN, YC). Consumes Bronze rows from KAN-32.
2. KAN-35, domain-key resolution and resolved_signals writer. Consumes staging rows from KAN-34 and `normalize_domain` (`src/huginn/silver/resolution.py`, tested).
3. KAN-36, manual review queue writer. Consumes the unmatched rows KAN-35 produces.

Gap carried forward: KAN-4 (fuzzy-match research) stays open. Every domain-less signal lands in `manual_review_queue` with no automated resolution path in this epic.

Integration artifact handed to Gold: rows in `silver.resolved_signals` with `resolved_company_key` and `key_derivation` set.

## 4. Gold (KAN-25)

Already done: schema (`db/schema/gold.sql`), Company and CompanyHistory update logic (`src/huginn/gold/dimensional.py`, tested against ADR-0002).

Build tasks:

1. KAN-40, Company upsert and CompanyHistory writer. Consumes resolved_signals rows from KAN-35 and `apply_company_update`.
2. KAN-41, CompanySignal fact writer. Consumes Company rows from KAN-40 and resolved_signals rows.
3. KAN-42, enrichment heuristic design. Artifact: a design note defining team-composition inference concretely, inputs restricted to company-owned pages and press releases per architecture document section 2's non-goals. Blocks KAN-43.
4. KAN-43, enrichment heuristic build. Consumes KAN-42's artifact, routes through KAN-40's writer so a change lands in `company_history`.

Gap flagged, not resolved here: KAN-20 (Gold Type 1 / Type 2 column classification) may already be answered in practice by `db/schema/gold.sql`'s CHECK constraints and `TYPE_2_TRACKED_FIELDS` in `dimensional.py`. Worth a short confirm-and-close pass rather than leaving it open as unresolved design work.

Integration artifact produced: a queryable `gold.company` table with current state, ready for the matching step (KAN-18, out of scope for this epic).

## 5. Verification (KAN-44)

Standalone task, not nested under a story. Consumes the full chain: an adapter (Ingestion), the Bronze write path, Silver staging and resolution, and both Gold writers. Asserts one company and its signal exist end to end from a fixture payload.

## Dependency chain, in build order

1. KAN-37 blocks KAN-26. KAN-38 blocks KAN-29. KAN-39 blocks KAN-30. Design artifacts before their adapters/ports.
2. KAN-27 blocks KAN-28. The job_runs table before the service wiring that writes to it.
3. KAN-32 blocks KAN-34. Bronze write path before Silver staging can read anything real.
4. KAN-35 blocks KAN-40. Resolved signals before Company upsert.
5. KAN-40 blocks KAN-41 and KAN-43. Company row before the signal fact and before enrichment.
6. KAN-42 blocks KAN-43. Enrichment design before its build.
7. KAN-40 and KAN-41 block KAN-44. Both Gold writers before the integration test.

## Gaps outside this epic's scope

1. KAN-4, fuzzy-match entity resolution. Silver ships domain-key only this epic.
2. KAN-7, YC ToS legal exposure. Adapter built anyway; the risk itself stays open.
3. KAN-8, v1 weighted scoring. Not started, waiting on real filtered-data volume.
4. KAN-18, matching step (resurfacing dedup, ICP reapplication). Explicitly excluded from KAN-21.
5. KAN-20, Gold Type 1 / Type 2 classification. Likely already answered by the existing DDL and code; needs confirmation, not new design.

## Findings from this planning pass

1. HN and YC access research already exists and is current (`docs/sources/*.md`, verified 2026-09-05). No new research needed there, only translation into build-ready fetch plans (KAN-38, KAN-39).
2. job_runs, named in the architecture document as part of orchestration (sections 3 and 5), has no schema anywhere yet. Proposed as a new `ops` schema (KAN-27), an implementation-level call, not an architectural one, flagged for review.
3. Team-composition enrichment was epic scope text without a design behind it. Split into a design task (KAN-42) ahead of the build task (KAN-43) rather than building against an undefined heuristic.

## Reference

Jira epic KAN-21 and its child stories (KAN-22, KAN-23, KAN-24, KAN-25). Architecture document sections 4 and 5. ADR-0001, ADR-0002. `docs/sources/hn-who-is-hiring.md`, `docs/sources/yc-directory.md`.
