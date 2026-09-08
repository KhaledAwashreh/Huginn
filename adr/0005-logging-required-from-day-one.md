# 0005: Logging and observability required from day one, not deferred

Status: Accepted
Date: 2026-09-08
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting)

## Context and Problem Statement

`BEST_PRACTICES.md` already documented general logging hygiene (error hiding, the log-and-throw anti-pattern, no library-code handler configuration) but never required that logging actually exist yet in Huginn's own code. It does not: KAN-27 (`ops/job_runs.py`) and KAN-29 (the HN adapter) both shipped with zero log statements. The architecture document's own section 4.1 names "a job that has silently stopped running" as a real failure mode, and KAN-31's cron-based orchestration means nobody is watching a terminal when the pipeline actually executes; logs are the only record of what happened on a given run. The decision-maker explicitly requires this addressed now, not filed as future debt the way the linter/type-checker choice (ADR-0004) was.

## Decision Drivers

1. Cron-based scheduling (KAN-31) means failures and silent stalls have no other visibility mechanism unless the code itself logs them.
2. The architecture document already treats "silently stopped running" as an explicit concern (section 4.1), but nothing implements the visibility that concern assumes.
3. Retrofitting logging into a larger, already-built codebase later costs more than building the habit in from the next ticket onward.
4. The decision-maker explicitly does not want this deferred, unlike ADR-0004's tooling choice.

## Considered Options

1. Defer logging to a dedicated observability ticket or epic later, once more of the pipeline exists (rejected)
2. Require logging conventions starting now, applied to every new ticket going forward, with the two already-shipped modules retrofitted as tracked debt rather than silently left as-is (chosen)

## Decision Outcome

Chosen option: 2. Standard library `logging`, one logger per module (`logger = logging.getLogger(__name__)`), no library-code module ever calls `logging.basicConfig()` or otherwise configures handlers itself, that stays the CLI entrypoint's job (KAN-31). Every pipeline-stage boundary logs: an adapter's `fetch()` logs record counts and duration; a Bronze/Silver/Gold writer logs rows written versus rows skipped; `IngestionService` logs a run's start and finish per source through `job_runs`; a genuine failure gets `logger.exception(...)` exactly once, at the point that handles it, never logged again on re-raise.

### Consequences

1. Good: a stalled or failing scheduled run becomes visible without attaching a debugger or re-running interactively.
2. Good: one consistent per-module logger pattern is simple to teach and simple to replicate across many small modules.
3. Bad: KAN-27 and KAN-29 need a retrofit pass to add logging that should have existed from their own first commit; tracked as debt, not silently accepted as-is.
4. Bad: this ADR settles code-level instrumentation only. It does not decide where those logs actually go in production (stdout captured by cron, a file, a shipped structured-logging backend) or who gets alerted on a failure; that operational question stays open.

## Pros and Cons of the Options

### Option 1: Defer to a later observability ticket

1. Good: keeps the current build wave narrowly scoped to what each ticket already describes.
2. Bad: every ticket shipped in the meantime accumulates the same retrofit debt KAN-27 and KAN-29 already have.
3. Bad: a cron-scheduled failure during the deferral window would be invisible, exactly the failure mode section 4.1 already worries about.

### Option 2: Require it now (chosen)

1. Good: closes the visibility gap immediately, before more modules ship without it.
2. Good: matches the urgency the decision-maker explicitly stated.
3. Bad: two already-merged tickets now carry acknowledged, tracked debt rather than a clean slate.

## Related

1. `docs/architecture.md` section 4.1: the "silently stopped running" concern this ADR gives a concrete answer to.
2. `CLAUDE.md` code standard 9: the convention itself, added the same day as this ADR.
3. `BEST_PRACTICES.md` section 6: the general logging hygiene rules (error hiding, log-and-throw, no library-code handler config) this ADR builds on rather than restates.
4. Jira KAN-27, KAN-29: the two modules needing a logging retrofit.
