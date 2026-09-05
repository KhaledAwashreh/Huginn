# Huginn — Reading List & Prior Art

**Status:** Reference · v0.1
**Last updated:** August 2026
**Companion to** `huginn-concept-doc.md`. Curated inputs for writing the design doc and building Phase 0.

---

## How to use this

Not a syllabus — a lookup table. Three tiers:

- ⭐ **Read before writing the design doc.** Six items, ~3 hours total.
- 📖 **Read when you reach that stage.** Grouped by pipeline stage.
- 🔍 **Reference.** Look up when stuck; don't read cover to cover.

Items tagged 🔴 map to an unresolved question in the concept doc.

---

## ⭐ Read first (the short list)

| #   | What                                                                                                                                                                                                   | Why it matters here                                                                                                                                              | Time   |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | **Design Docs at Google** — Malte Ubl · [industrialempathy.com/posts/design-docs-at-google](https://www.industrialempathy.com/posts/design-docs-at-google/)                                            | Best single article on the genre. Core idea: a design doc documents *trade-offs considered*, not the final system. The section the current arch stub is missing. | 20 min |
| 2   | **Documenting Architecture Decisions** — Michael Nygard · [cognitect.com/blog/2011/11/15/documenting-architecture-decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) | Every 🔴 in the concept doc is an ADR waiting to be written. The changelog records *what* changed, never *why*.                                                  | 10 min |
| 3   | **Rules of Machine Learning** — Martin Zinkevich · [developers.google.com/machine-learning/guides/rules-of-ml](https://developers.google.com/machine-learning/guides/rules-of-ml)                      | Rule #1: don't use ML, use heuristics. Read before writing any scoring code. Directly governs §6.6.                                                              | 45 min |
| 4   | **Functional Data Engineering** — Maxime Beauchemin · search title on Medium                                                                                                                           | Immutable, idempotent, partitioned batch tasks. Justifies storing raw payloads forever — the thing that lets you re-score weekly without re-scraping.            | 15 min |
| 5   | **C4 Model** — Simon Brown · [c4model.com](https://c4model.com)                                                                                                                                        | Read the Context and Container levels only. Skip Component and Code — they rot. Renders as Mermaid in Obsidian.                                                  | 30 min |
| 6   | **hiQ v. LinkedIn — the full arc** (2019 → 2022)                                                                                                                                                       | The commonly cited holding is only half the story. See §Legal below; it changes what §8 should say.                                                              | 20 min |

---

## 📖 By pipeline stage

### Ingestion — connector/adapter design

| Resource                                                                                                                                                                    | Take-away                                                                                                                                                                                                                                          |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Singer spec** · [singer.io](https://www.singer.io)                                                                                                                        | Connector contract: `discover` → `read(state)` → emit records + new bookmark. Steal the **state/cursor** concept even if you never use the runtime — it's what stops a re-run from re-ingesting HN's entire archive.                               |
| **Airbyte CDK** · [docs.airbyte.com](https://docs.airbyte.com) + `airbyte-integrations/connectors/` in [github.com/airbytehq/airbyte](https://github.com/airbytehq/airbyte) | Read two or three source connectors for shape. Note how incremental vs. full-refresh is declared, not coded.                                                                                                                                       |
| **Meltano** · [meltano.com](https://meltano.com)                                                                                                                            | The orchestrated version of the above. Almost certainly overkill for two sources — read to know what you're opting out of.                                                                                                                         |
| **Hexagonal Architecture** — Alistair Cockburn · [alistair.cockburn.us/hexagonal-architecture](https://alistair.cockburn.us/hexagonal-architecture/)                        | The pattern name for one `SourceAdapter` interface, N implementations. §7 already splits into two adapter families (live/scrape vs. newsletter-parse) — that's the boundary.                                                                       |
| **HN official API** · [github.com/HackerNews/API](https://github.com/HackerNews/API)                                                                                        | Firebase-backed, documented, no auth, no rate limit drama. Confirms §7's "easiest, most reliable."                                                                                                                                                 |
| **Existing HN Who's-Hiring parsers** — search GitHub before writing one                                                                                                     | The thread structure has edge cases (nested replies, format drift month to month, people who ignore the template). Someone has already hit them.                                                                                                   |
| **changedetection.io** · [github.com/dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io)                                                           | Page-diff monitoring. Relevant to VC portfolio boards with no JSON endpoint.                                                                                                                                                                       |
| **YC directory**                                                                                                                                                            | Reported to be Algolia-backed rather than server-rendered — several community scrapers hit the index directly. **Verify current setup and ToS yourself** before depending on it; this is exactly the kind of thing that changes without notice. 🔴 |

### Storage & entity resolution 🔴

> The sleeper hard problem. "Acme AI" (HN), "Acme" (YC), "Acme AI, Inc." (VC board) are one company. Currently one word in §6.3; it's a subsystem.

| Resource                                                                                                    | Take-away                                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Splink** · [github.com/moj-analytical-services/splink](https://github.com/moj-analytical-services/splink) | Probabilistic record linkage, actively maintained. Docs explain the Fellegi–Sunter model better than most textbooks.                                                                                                             |
| **dedupe** · [github.com/dedupeio/dedupe](https://github.com/dedupeio/dedupe)                               | The Python classic. Active-learning labelling loop is the interesting part.                                                                                                                                                      |
| **Data Matching** — Peter Christen (Springer)                                                               | The standard textbook. Reference, not a read-through.                                                                                                                                                                            |
| **tldextract** · [github.com/john-kurkowski/tldextract](https://github.com/john-kurkowski/tldextract)       | Practical shortcut: **the registered domain is the canonical key.** Normalise (strip `www`, resolve redirects once). Domain match ≈ same company most of the time; name matching is the fallback, not the primary. Worth an ADR. |
| **Medallion architecture** (bronze/silver/gold) — Databricks' name for a generic idea                       | Raw payload → normalised entity → scored. Non-negotiable here: scoring changes weekly in Phase 0, re-scoring stored data is free, re-scraping is rate-limited and sometimes impossible (the HN thread rolls off).                |

### Scoring & feedback 🔴

| Resource | Take-away |
|---|---|
| **Introduction to Information Retrieval** — Manning, Raghavan, Schütze · free at [nlp.stanford.edu/IR-book](https://nlp.stanford.edu/IR-book/) | **Ch. 9 (relevance feedback) is the chapter.** The Rocchio algorithm — bump weights for features in 👍 items, decay for 👎 — is ~20 lines and interpretable. That's what §6.6 should be. |
| **Adaptive information filtering / TREC Filtering Track** | The academic name for exactly this problem: standing profile, document stream, push the relevant ones. Search term for finding real prior work rather than recommender-system material that assumes millions of interactions. |
| **Practical Recommender Systems** — Kim Falk (Manning) | Content-based filtering chapters. Book-length; skim. |
| **MadKudu / Keyplay blogs** | The best public writing on "turn a fuzzy fit definition into a number." Vendor content, but substantive on methodology. |

**Do the arithmetic before designing the feedback loop:** 5 leads/week × 50 weeks = ~250 labels/year, one user. That is not a training set. Rules + weight nudging, not a model.

**Constraint to write into the design doc:** §5 promises plain-language match reasoning per entry. That forces a score **decomposable into per-feature contributions** — additive/linear. Any model that can't say *which* feature fired is disqualified by the product spec itself. This closes off options later, so state it explicitly.

### Orchestration & delivery

| Resource | Take-away |
|---|---|
| **Dagster software-defined assets** · [docs.dagster.io](https://docs.dagster.io) | Read for the *concept* even if Phase 0 is cron + a `job_runs` table. "This table is derived from those sources" beats "run this script at 6am" — and makes backfills tractable. |
| **Outbox pattern** (search: transactional outbox) | A `matches.status` state machine (`new → surfaced → sent/dismissed`) so a crashed digest job doesn't double-send or silently skip a week. |
| **Data freshness / observability** (Great Expectations, or hand-rolled) | **A source returning zero rows is a bug, not a quiet week.** Newsletter parsers fail silently; you won't notice for a month. Cheap version: per-source last-successful-row timestamp, alert at 2× expected cadence. |
| **Postgres row-level security** | Phase 2 multi-tenancy. Shared pool + per-tenant `matches` join table is the standard shape — §11 already has it right. |
| **pgvector** · [github.com/pgvector/pgvector](https://github.com/pgvector/pgvector) | Semantic sector matching without a second datastore. Postgres-for-everything is the right Phase 0 call. |

---

## 🔍 Prior art

### Codebases worth actually reading

| Project | Why |
|---|---|
| **Miniflux** · [github.com/miniflux/v2](https://github.com/miniflux/v2) | ⭐ Best single codebase to read. Go RSS reader with digest emails — the exact pipeline shape: poll heterogeneous sources → dedupe → store → deliver. Small and clean enough to read in an evening. |
| **Airbyte source connectors** | Connector contract in practice. |
| **changedetection.io** | Scraping targets with no API. |
| **Microsoft `recommenders`** · [github.com/recommenders-team/recommenders](https://github.com/recommenders-team/recommenders) | Reference for algorithm choice. Assumes far more data than you'll have — read as a map, not a manual. |

### Commercial analogs

Read their docs and engineering/methodology posts, not their landing pages.

| Product | What to learn |
|---|---|
| **Clay** | Closest architectural analog. Waterfall enrichment, signal triggers, ICP scoring — data model described openly in their docs. |
| **Common Room** | Signal capture from public community sources. Nearest cousin. |
| **Keyplay**, **MadKudu**, **Pocus**, **Koala** | Fit/PQL scoring methodology. Keyplay writes most openly about "signals." |
| **UserGems** | Built on *one* signal (job changes), done well. The strongest counter-argument to the multi-source plan in §7 — one great signal may beat eight mediocre ones. Worth taking seriously before Phase 1. |
| **Harmonic** | Listed as a source in §7; also a competitor. Understand as both. |
| **Ocean.io**, **Warmly**, **Trigify**, **Apollo**, **Clearbit** | 20 minutes each, landscape awareness only. |

---

## Legal & ToS

> The concept doc's §8 is directionally right but cites the wrong risk, and omits the bigger one.

| Item | Why it matters |
|---|---|
| **hiQ v. LinkedIn** (9th Cir. 2019, reaffirmed 2022; D. Ct. Nov 2022; settled) | Commonly cited as "scraping public data is legal." Accurate reading is narrower: no **CFAA** violation, but the district court found hiQ **breached the User Agreement**, and hiQ settled under injunction. The risk is **contract, not computer-access law** — so what matters is whether you accepted terms, not whether the data was public. |
| **Van Buren v. United States** (SCOTUS 2021) | Narrowed the CFAA generally. Supports the above. |
| **Meta v. Bright Data** (N.D. Cal. 2024) | Scraping while *logged out* wasn't a ToS breach — no terms were ever accepted. **Practical rule: never authenticate to a source you scrape.** |
| **GDPR Art. 6(1)(f)** — legitimate interest | Requires a documented balancing test. Not mentioned anywhere in the concept doc. |
| **GDPR Art. 14** — notice when data comes from a third party | Notification duty within one month when you didn't collect from the subject. Most vendors lean on the Art. 14(5)(b) "disproportionate effort" exemption; contested. |
| **Bisnode / Polish DPA fine** (2019, ~€220k) | Canonical case for exactly this pattern: scraped public business-registry data, didn't notify. Read this one. |
| **EDPB legitimate-interest guidance**; **ICO direct-marketing guidance** | The ICO's is post-Brexit but the clearest plain-English writing on the topic. |
| **B2B cold email by jurisdiction** — Spain (LSSI) vs. NL / Ireland | IE and NL have B2B exemptions for corporate addresses; Spain is stricter. Lower risk since a human sends manually, but §8 should carry a line on it. |

**Cheapest de-risking available:** keep people out of the pool entirely. Store organisations, signals, and URLs — not founder names or roles. §5 already links to a LinkedIn *search* rather than a profile; extend that principle to the whole schema and most GDPR exposure disappears. Worth an explicit ADR: *"The pool stores organisations, not people."*

---

## Doc-set templates (for the docs themselves)

| Template | Use |
|---|---|
| **MADR** · [adr.github.io/madr](https://adr.github.io/madr/) | ~15-line markdown ADRs. Fits Obsidian directly. |
| **adr-tools** · [github.com/npryce/adr-tools](https://github.com/npryce/adr-tools) | CLI scaffolding if numbering by hand gets tedious. |
| **arc42** · [arc42.org](https://arc42.org) | Heavy for solo work. Lift sections 8 (crosscutting concepts), 9 (decisions), 11 (risks & technical debt). |
| **Oxide RFDs** · [rfd.shared.oxide.computer](https://rfd.shared.oxide.computer) | RFD 1 is a good read on *process*: numbered, discussed, then frozen. |
| **Structurizr DSL** · [structurizr.com/dsl](https://structurizr.com/dsl) | Diagrams-as-code for C4 — one model, many views. Overkill at Phase 0. |
| **Mermaid** (native in Obsidian) | `flowchart` for the pipeline, `erDiagram` for §11. Replaces the ASCII diagrams, which are charming but unmaintainable. |

---

## Open threads this reading should close

| Concept doc 🔴 | Read | Then write |
|---|---|---|
| §9 "Which 2 sources first" — **blocking** | HN API, YC directory ToS | ADR-0001 |
| §6 team-composition signal | Rules of ML; TREC filtering | ADR on proxy signals |
| §6.3 dedup strategy | Splink docs, tldextract | ADR: domain-as-canonical-key |
| §8 ToS & data risk | Legal table above | Rewrite §8; ADR: organisations-not-people |
| §9 scoring weights: user-editable or feedback-only | IR-book ch. 9 | ADR on Rocchio-style nudging |

---

## Changelog
- **v0.1** — Initial reading list. Split into read-first / by-stage / reference; added prior-art and legal sections keyed to open questions in the concept doc.
