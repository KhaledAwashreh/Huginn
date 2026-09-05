# Huginn — Session Handoff (2026-09-05)

**Why this file exists:** this session ran a long grilling/research pass on the Huginn MVP arch doc and set up Atlassian MCP access. Most of the substance is also saved to persistent memory (auto-loaded in future sessions), but this is a single readable snapshot in case context resets mid-stream — e.g. after the `/clear` needed to pick up the new Atlassian MCP tools.

**Not done yet:** the actual Huginn Architecture Document (the original deliverable) has not been drafted. This session produced *inputs* to it — locked decisions and source research — not the doc itself. Scoring (features/weights) is also still open. See "Next steps" at the bottom.

---

## Goal for this whole effort

Write a Huginn arch doc for an MVP: simplest UI, most general implementation, sound design/patterns. Approach: run the `grilling` skill (Matt Pocock's `/grill-me`, pulled from GitHub and registered globally at `~/.claude/skills/grill-me` and `~/.claude/skills/grilling` since it wasn't installed) to surface and close every open decision before drafting.

## Pre-existing docs (read, not modified)

- `Huginn Arch Dcument.md` — a stub, mostly empty (just problem/vision).
- `huginn-concept-doc.md` v1.3 — the product vision doc. Promises a plain weekly digest, explicitly excludes CRM/outreach automation.
- `huginn-diagrams.md` — Mermaid diagrams + a "Not yet specified" table that mapped most of this session's agenda.
- `huginn-reading-list.md` — curated prior art (medallion architecture, Singer spec, hexagonal ports-and-adapters, Splink/dedupe, Dagster concept, outbox pattern, hiQ v. LinkedIn legal analysis, "organisations not people" ADR recommendation).
- `Entites.md` — a richer, CRM-shaped entity schema (Activity, versioned/multi-turn Communication drafting) that turned out to conflict with the concept doc's minimal scope. Reconciled in Q1 below.

## Decisions locked this session

**Q1 — Scope reconciliation (concept doc vs. `Entites.md`).** Keep the general/richer schema from `Entites.md` (matches "most general implementation"), but the MVP code path only writes a thin slice of it: a digest send creates exactly one `Match` + one `Communication` row per company, auto-marked `Sent`. `CommunicationVersion`/`CommunicationRevision`/`CommunicationTurn`/`Activity` exist in the schema but nothing in MVP drives them. Corollaries: no chatbot UI in MVP; ICP capture is a one-time plain-text-to-structured-filter form, not conversational; feedback loop (`MatchFeedback`) is schema-ready but not wired to scoring yet.

**Q2 — Tech stack.** Python, confirmed explicitly. (`Entites.md`'s PascalCase/`DateTimeOffset`/`GUID` naming reads like C#/.NET but was incidental, not a real preference.)

**Q3 — Sources.** HN "Who's Hiring" + YC directory locked as the two MVP ingestion sources. All other candidates researched for future phases — see "Source research" below.

**Q4 — Team-composition / soft-signal-enrichment** (was the one unresolved node in `huginn-diagrams.md` §3):
1. Person-level insight only from company-owned "Team/About" pages + press releases. LinkedIn/Glassdoor scraping was proposed, then set aside — it would reopen a risk call the reading list already resolved the other way (hiQ v. LinkedIn, "organisations not people" ADR-recommendation). `Entites.md`'s pre-existing `Employee` entity means person-level data isn't new scope, just not sourced from third-party platforms.
2. No graph-traversal/ML "predict current needs and goals" model for MVP — explicitly TBD and out of scope, hand-authored rule/heuristic only if anything ships here at all.
3. Enrichment runs only on companies that already passed cheap filters (stage/sector/recency) — never the full pool.

**Q5 — Entity resolution — closed.** Domain-as-canonical-key first; fallback = normalize → strip legal suffixes (OpenSanctions suffix list) → Jaro-Winkler (~0.92 auto-match, ~0.85–0.92 manual-review band, below that no-match) + token-Jaccard for word-order variance. Ambiguous band goes to a manual-review queue, not an auto-decision. Splink/`dedupe` explicitly deferred until there's a real labeled-pair backlog. User knowingly accepted this as researched-not-personally-verified technical debt for MVP (no personal background in entity resolution), with the manual-review backlog as the trigger to learn it properly later.

## Source research (`Huginn/sources/*.md`, one file per source)

All verified live (fetched real docs/pages, not memory), written the same week:

| Source | Verdict |
|---|---|
| `hn-who-is-hiring.md` | MVP source. Official Firebase API, no auth/rate limit. ~1 in 9 sampled posts had no extractable URL — drives the entity-resolution fallback need. |
| `yc-directory.md` | MVP source. Algolia-backed, public embedded search key, no official API. **Live ToS-vs-robots.txt conflict**: ToS bans scraping explicitly, robots.txt silent on direct Algolia calls. `website` field reliably present. |
| `vc-portfolio-boards.md` | Deferred. Only Index Ventures is actually Getro-powered; Sequoia/a16z/Greylock need bespoke adapters. **Greylock's robots.txt explicitly blocks `ClaudeBot`.** |
| `ramp-vendor-reports.md` | Deferred. No API; only `ramp.com/vendors/categories/*` is structured enough to scrape. Biased demand-side signal, not general growth. |
| `harmonic-hot-25.md` | Deferred. Quarterly, partially gated page; real API is enterprise-only (~$25k/yr est). |
| `newsletters.md` | Deferred. All 4 (Founders You Should Know, Next Play, Early Days, a16z Build) are **Substack with public RSS** — overturns the original Gmail-inbox email-parsing plan. |
| `cordis-api.md` | Deferred. Free, API-key auth, but async bulk-extraction job, not live query. Query grammar undocumented. |
| `opencorporates-api.md` | Likely dead end. Free tier requires open share-alike licensing on derived data — incompatible with private commercial use. Cheapest compatible tier: ~£2,250/yr for 500 calls/month. |
| `indeed-hiring-posts.md` | **Not viable.** Self-serve API killed 2023; current APIs enterprise-only; robots.txt blocks scrapers and AI crawlers by name; ToS bans bots; live test hit a Cloudflare CAPTCHA immediately. |

## Pipeline architecture standards check

`Huginn/architecture-notes/data-pipeline-standards.md` — checked the existing plan (medallion architecture, Singer-style contract, hexagonal ports-and-adapters, transactional outbox) against Sept-2026 practice. **Mostly confirms, some refinements**:
- Entity resolution recipe above came from this doc.
- Cursor-less sources (YC's Algolia backend, any scraping): use a self-generated content hash (SHA-256 over normalized fields) as the watermark instead of a source cursor; query YC's Algolia search-only key directly rather than scraping rendered HTML.
- Orchestration: cron + `job_runs` table still the right default. Dagster+ got *more* expensive for solo users in May 2026 (reinforces "don't adopt"). Prefect OSS and GitHub Actions `schedule:` are the named upgrade paths if ever needed.
- Observability: adopt Pandera for per-adapter schema-drift assertions (fits ports-and-adapters seams), keep the freshness/zero-row-alert table as the separate run-level layer.
- New tool worth adopting: `dlt` (dlthub) as a lightweight Python-native way to build source adapters, instead of hand-rolling the Singer contract.

## Memory saved (persists automatically in future sessions)

- `huginn_mvp_scope_decisions.md` (project memory) — everything in "Decisions locked" above.
- `huginn_source_research.md` (reference memory) — pointer to `Huginn/sources/*.md` with headline findings.
- Both indexed in `MEMORY.md`.

## Atlassian MCP setup

- Registered: `claude mcp add --transport http --scope user atlassian https://mcp.atlassian.com/v1/mcp/authv2` (official Atlassian remote MCP server, GA Feb 2026 — covers Jira, Confluence, Jira Service Management, Bitbucket, Compass).
- OAuth completed by the user in a real interactive terminal (the in-chat `!` prefix can't complete it — no TTY for the browser-callback flow).
- `/mcp` confirms **connected** at the config level.
- **Open issue:** the session that did the setup couldn't see the Atlassian tools via `ToolSearch` — it loaded its tool manifest before the connection existed. Needs a fresh session (or `/clear`) to pick up the new tools. **Verify this first in the new session** before assuming Atlassian tools are usable.

## Next steps

1. In a fresh session: confirm Atlassian MCP tools are actually callable now (ToolSearch or just try one).
2. Resolve scoring — which features feed the score (stage, sector, funding-recency, source-quality, the Q4 team-composition signal) and what initial weights to start with, since there's no historical data to derive them from. Flagged in the reading list as "the highest-value open piece in the system." Nothing decided on this yet.
3. Once scoring is resolved, actually draft the Huginn Architecture Document itself — this session only produced inputs to it (decisions + source research + pipeline-standards findings), the doc hasn't been written.
4. Minor open thread: `huginn-concept-doc.md` §9 still nominally lists "which 2 sources first" as blocking even though it's now closed (HN + YC) — worth a one-line update to that doc, or a proper ADR file, when convenient.
