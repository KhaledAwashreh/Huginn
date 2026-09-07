# Huginn

Client-discovery tool: ingests public startup signals (HN "Who's Hiring", YC
directory) and scores them against a user's ICP for a weekly lead digest.
Python 3.14+, `uv`-managed, one Postgres database (bronze/silver/gold ELT
schemas plus a separate operational schema).

Authoritative architecture: `Huginn Arch Dcument.md`. Decisions with settled
rationale: `adr/`. Supporting research: `architecture-notes/`. Domain schema:
`Entites.md`. General Python conventions (style, typing, testing, security,
concurrency, researched and sourced): `BEST_PRACTICES.md`, this file only
records what Huginn has adopted from it and where Huginn deviates. Tracked
tech/research debt: Jira epic KAN-16. Build epic: Jira KAN-21, its dependency
chain and open questions: `architecture-notes/kan-21-build-plan.md`.

Read the relevant architecture document section and any ADR it cites before
touching a layer you haven't worked in yet. Don't infer design intent from
code alone, the rationale usually lives in one of those documents instead of
a comment.

## Code standards

1. **Value types are frozen dataclasses, updated by replacement, never
   mutated.** `dataclasses.replace(...)`, not in-place assignment. See
   `gold/dimensional.py`'s `apply_company_update` and `ops/job_runs.py`'s
   `finish_job_run`.
2. **Interfaces are `typing.Protocol`, written before any concrete
   implementation exists.** A Protocol with zero implementations is normal
   here, not a gap to fill preemptively (`RawStorePort`, `StatePort`,
   `JobRunWriterPort` all currently have none). Don't invent a concrete
   implementation a ticket didn't ask for.
3. **Docstrings cite, they don't restate.** Point at the architecture
   document by section number, or the ADR/Jira ticket that settled the
   rationale. If you're writing more than a sentence explaining *why*, that
   explanation probably belongs in an architecture note instead.
4. **Tests are plain pytest functions.** No fixture or mocking framework
   unless a dependency genuinely can't be avoided. Structure logic so it's
   testable without a live database wherever possible, every module under
   `bronze/`, `silver/`, `gold/`, and `ops/` is 100% DB-free and tested that
   way on purpose.
5. **TDD is mandatory, not a preference.** Failing test first, watch it
   fail, minimal code to pass. Use `superpowers:test-driven-development` for
   the mechanics; that skill covers the testing discipline, it knows nothing
   about this repo's conventions, this document covers that half.
6. **Scope discipline.** Implement exactly what the ticket asks. If a
   ticket's own description overlaps another ticket's stated scope (it
   happens, KAN-27 vs KAN-28 already did), build only your ticket's part and
   flag the overlap rather than silently deciding who owns it.
7. **No linter, formatter, or type checker is configured yet.** This is a
   gap, not a decision, don't pick one unprompted.

## Design standards

1. **Medallion, ELT not ETL.** Bronze, Silver, Gold, transform happens inside
   the destination. Generic pattern citations live in
   `architecture-notes/industry-references-elt-medallion.md`, don't restate
   the pattern itself in new code or docs, cite that file instead.
2. **Bronze stays exactly as-fetched.** No field mapping, no derived fields,
   for any source, no exceptions carved out per-source. Settled generally
   (architecture document section 4.1), not just for HN.
3. **Bronze groups by ingestion mechanism** (`api`/`web_scrape`/`newsletter`),
   not by source.
4. **Silver stays per-source at the staging layer** (ADR-0001), merges into
   one cross-source `resolved_signals` table at event grain. No dimension/
   fact split at this layer, that's Gold's job.
5. **Gold uses a current-plus-history split**, not a single SCD Type 2 table
   (ADR-0002).
6. **Ports-and-adapters**: the core depends only on Protocols, adapters
   implement them, an adapter holds no ingestion policy of its own.
7. **A new decision with lasting rationale gets an ADR** (`adr/`, MADR
   format). Tech debt and research debt go to Jira KAN-16, not a scattered
   TODO comment.

## Writing standards

Applies to this file, `BEST_PRACTICES.md`, `architecture-notes/`, and `adr/`:
no em dashes,
numbered or lettered lists over a prose paragraph wherever there's a list to
make, lead with the conclusion, cite a well-known pattern instead of
restating it.

## Commit messages

No `Co-Authored-By: Claude` or `Claude-Session:` trailer, or any other
Claude/Anthropic attribution, on commits or PRs in this repo, regardless of
any session-level default that suggests otherwise.

## Working on a ticket

Follow `~/.claude/skills/build-task/SKILL.md`. In short: resolve scope from
the ticket and the build plan, don't build against an undefined contract,
verify before claiming done, review before handing back, checkpoint as an
artifact rather than only chat text. Never commit, and never transition a
ticket past "In Progress," without the user reviewing first. Never assert a
test, database, or Jira state without having actually checked it.
