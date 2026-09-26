# 0014: Pipeline entry point, stage order, and dependency-aware skip-on-failure

Status: Accepted
Date: 2026-09-26
Deciders: Khaled Awashreh

## Context and Problem Statement

Ingestion, Bronze, Silver, and Gold were each built and tested in isolation
(KAN-22 through KAN-41), but nothing called the Silver or Gold writers:
`python -m huginn.elt.ingestion` only ever ran Ingestion. Three things had
to be decided together, because each depends on the others: where a full
run's entry point lives, what order its stages run in and what each
depends on, and what happens when one stage fails.

The stage-failure question was initially framed as "does one stage's
failure abort the whole run," motivated by a specific worry: the
resolution stage (`SignalResolver.resolve_all()`) makes on the order of
4,600 sequential per-domain HTTP reachability checks, so a DNS or HTTP
blip partway through looked like it could wedge the entire run. Tracing
the actual code (`huginn.elt.silver.resolution.check_domain_reachable`
and its `_request_with_retry` helper) showed that framing was wrong:
every network exception a reachability check can raise
(`Timeout`, `ConnectionError`, any other `RequestException`, and the DNS
failures `_resolves_to_public_address` can raise) is already caught
inside that function and turned into a plain `False`/`"unresolved"`
result, never an exception. A flaky domain is misclassified for manual
review, not a crash. So the real question was narrower than first posed:
not "how do we tolerate network flakiness," which is already handled, but
"what should happen when a stage genuinely fails," which today can only
be a real Postgres failure, an unguarded parse defect (the same class of
bug E0 fixed for YC staging and this same effort fixed for HN staging), or
an undiscovered bug.

## Decision Drivers

1. Two industry-standard orchestrators, checked directly rather than
   assumed, both default to letting independent work continue past a
   failure rather than aborting everything: dbt's `dbt run`/`dbt build`
   only skip models that depend on a failed one, and `--fail-fast`/`-x`
   (abort-everything) is an opt-in flag, explicitly not the default
   (dbt docs, "Failing fast"). Airflow's default `trigger_rule` is
   `all_success`, a task runs only if its own upstream succeeded; a task
   with no dependency on a failure runs on schedule regardless.
2. Architecture document section 2: "no real-time alerts, weekly batch by
   design." A failed run costs one week of staleness, not an outage.
3. Every write in this pipeline is an idempotent upsert keyed on a stable
   identity (Bronze's content hash, Silver's `(source, stable_id)`, Gold's
   `domain` and `(source, source_stable_id)`), so rerunning the whole
   pipeline after a failure recovers cleanly with no cleanup step.
4. The alternative once seriously considered, classifying a failure as
   database-vs-network before deciding whether to continue, has no
   failure case left to classify at the resolution stage specifically
   (Decision Driver in the Context section above), and would need a real
   API change (the domain repository would have to expose a
   reachable-signal read) to implement anywhere else, not a one-line
   policy switch.
5. `job_runs.source` (Jira KAN-27, `ops.sql`) already exists as a
   freeform TEXT column with no foreign keys in or out, so recording a
   pipeline stage under it, alongside the ingestion sources it already
   records, needs no schema change beyond the new `status` value below.

## Considered Options

1. Dependency-aware skip-on-failure: a stage runs only if every stage it
   depends on succeeded; an unrelated stage is unaffected. (chosen)
2. Abort-on-first-failure: any stage failing stops the whole run.
3. Classify failures (database/logic vs. network) and continue past a
   network-only failure specifically, abort on anything else.

## Decision Outcome

Chosen option: 1, dependency-aware skip-on-failure, matching dbt's and
Airflow's own default rather than either alternative. Option 2 was the
original plan and was rejected on direct pushback during design review:
a single row's network hiccup should not cost 4,999 other rows their
whole run, and once the resolution stage's real isolation behavior was
traced (Context above), abort-on-first-failure had no remaining
justification strong enough to prefer it over the dependency-aware
default two mainstream tools already ship. Option 3 was rejected because
the failure mode it exists to handle, a network blip inside the
resolution stage, cannot actually reach that stage's caller as an
exception, so the classification work would guard against a case that
does not occur in this codebase today.

### Consequences

1. Good: a stage with no dependency on a failure runs regardless of that
   failure, matching Driver 1 and the direct feedback that motivated
   revisiting the original abort-on-first-failure plan.
2. Good: `ops.job_runs` gains a `SKIPPED` status distinct from `FAILED`,
   so an operator reading the table can tell "this stage never ran
   because its dependency didn't succeed" apart from "this stage ran and
   broke," rather than the two looking identical.
3. Good: `Stage.depends_on` is explicit, plain data (a tuple of stage
   names), so the dependency graph is readable from `build_stages` alone
   without tracing `run_stages`' control flow.
4. Neutral: `ops.job_runs.status`'s CHECK constraint widens from three
   values to four (`db/schema/ops-job-runs-skipped-status.sql`), an
   idempotent `ALTER` for existing databases, following the same
   drop-then-add pattern `gold-company-scale.sql` established.
5. Bad, known and accepted: the `ingestion` stage is one unit covering
   both HN and YC (matching `IngestionService.run_once()`'s own existing
   per-source isolation, which already writes its own `hn`/`yc` rows to
   `ops.job_runs`), so if either source's fetch fails, both
   `silver.hn_staging` and `silver.yc_staging` are skipped, even though
   the source that did succeed has fresh Bronze rows ready to stage. A
   future refinement could split ingestion into a stage per source to
   close this gap; not done here, to avoid changing
   `IngestionService`'s already-tested internal behavior as part of this
   decision.
6. Bad, known and accepted: dependency-aware skip does not, by itself,
   distinguish "this stage's dependency has never once succeeded" from
   "this stage's dependency failed only on this run but has real data
   from a prior run already sitting in its table." A skipped downstream
   stage does not get a chance to run against that older, still-valid
   data. Every staging/resolution/Gold write in this pipeline is an
   idempotent upsert over persistent tables (Driver 3), so this is a
   real but bounded cost: a skipped stage produces no fresher output this
   run, it does not lose or corrupt what a prior run already wrote.

## Pros and Cons of the Options

### Option 1: dependency-aware skip-on-failure (chosen)

1. Good: matches the default behavior of two widely used, independently
   maintained orchestrators (dbt, Airflow), not a bespoke policy invented
   for this codebase.
2. Good: an unrelated stage is never held hostage by a failure it has no
   real dependency on.
3. Bad: the dependency graph has to be declared and kept accurate by
   hand (`Stage.depends_on`); a missing edge would let a stage run against
   incomplete upstream data without anything flagging it.

### Option 2: abort-on-first-failure

1. Good: simplest to implement and reason about, one boolean per run.
2. Bad: exactly the case a real user objected to during design review,
   4,999 good rows' worth of downstream work blocked by one row's
   unrelated failure, made worse by depending on a stage
   (`silver.hn_staging`) that structurally cannot be crashed by row-level
   network failures to begin with (Context above), so the harm was never
   buying any real safety.

### Option 3: classify failures, continue past network-only

1. Good: would have been a genuine middle ground if the resolution
   stage's network calls could actually raise past its own boundary.
2. Bad: they cannot (Context above), so this option spends real
   implementation cost (a new port method to distinguish failure
   classes) defending against a scenario that does not occur in the
   current code.

## Related

1. Architecture document section 5 (ingestion), section 4
   (bronze/silver/gold), and section 2 ("weekly batch by design").
2. `docs/superpowers/plans/2026-09-26-yc-staging-resilience-handoff.md`
   ("E1" through "E4"), the handoff this ADR closes out; its original
   stage table and dependency reasoning are carried into
   `src/huginn/elt/__main__.py`'s `build_stages` largely unchanged, only
   the failure policy itself (its "E2") was revised here.
3. `huginn.elt.silver.resolution.check_domain_reachable` and
   `_request_with_retry`, the code whose tracing revised the original
   "network blip" framing.
4. `huginn.ops.job_runs.JobRunStatus`, `db/schema/ops.sql`, and
   `db/schema/ops-job-runs-skipped-status.sql`, the `SKIPPED` status this
   decision adds.
5. ADR-0006 (network call held outside any open database scope in
   `SignalResolver`), the prior decision that makes the resolution
   stage's network isolation possible in the first place.
