# 0006: SignalResolver.resolve_all() opens two connection scopes, not one

Status: Accepted
Date: 2026-09-17
Deciders: Khaled Awashreh

## Context and Problem Statement

`huginn.elt.silver.ports`'s module docstring states a deliberate, project-wide
rule: every Silver port bundles reads and writes into one connection scope,
so "a run over N records costs one connect rather than one per record and a
mid-loop failure leaves no partial batch behind," and so "its reads and
writes share a single consistent snapshot." `SignalResolver.resolve_all()`
followed this exactly: `with self._repository:` opened once, wrapping a read
of every staged signal, a per-row call to `resolve_signal()`, and an upsert,
all in one transaction.

KAN-62 added a live network call inside `resolve_signal()`
(`check_domain_reachable()`, an HTTP HEAD/GET reachability check) without
changing this shape. The transaction's duration is no longer bounded by
database work; it is bounded by however long every domain's network check
takes, summed across the whole batch. At this project's own stated real
volume (6,253 domain-normalized signals from one ingestion pass), CodeRabbit's
review of KAN-62's PR calculated a worst case of roughly 33 hours of HTTP wait
time inside one open Postgres transaction (worst case ~20s per domain: a HEAD
attempt plus one retry, then a GET fallback attempt plus one retry, each at
a 5s timeout). Even far short of that ceiling, holding row locks and a
database connection open for a duration governed by unpredictable external
I/O risks idle-in-transaction timeouts (which would roll back the entire
batch, discarding every already-correct resolution in it), connection pool
exhaustion, and lock contention against anything else touching
`silver.resolved_signals`.

## Decision Drivers

1. The batch cannot avoid touching the database before it knows what to
   check: the staged signals (and their `website` fields) live in
   `silver.hn_postings`/`silver.yc_listings`, so some database read has to
   happen before any reachability check can run.
2. `ports.py`'s stated rationale for one scope ("no partial batch left
   behind") is a real, worthwhile guarantee in general, but `SignalResolver`
   is not actually relying on it for correctness: `resolve_all()`'s own
   docstring already states every row is rewritten on every run "even when
   nothing changed," meaning the batch is designed to be safely re-run from
   scratch. A partial write from a mid-batch crash is not a data-integrity
   loss here, only an incomplete run that a subsequent run repeats and
   completes, the same idempotent-upsert behavior this orchestrator already
   has.
3. `PostgresConnectionScope` (composed by `PostgresSignalResolutionRepository`)
   already supports being entered and exited more than once on the same
   instance: `__enter__` opens a fresh `psycopg.connect(...)` each call and
   `__exit__` fully closes and resets state, so no change to the port's
   implementation is needed, only to how `SignalResolver.resolve_all()`
   calls it.
4. Parallelizing the reachability checks (a bounded thread pool, ADR-0003)
   would shrink the wall-clock total but does not address the actual
   problem named here: however long the checks take, a database transaction
   should not be open for any of it. That is a separate, complementary
   optimization, not an alternative to this decision.

## Considered Options

1. Keep one connection scope for the whole batch, parallelize the
   reachability checks with a bounded thread pool to shrink wall-clock time.
2. Split `resolve_all()` into two connection scopes: a short read scope,
   then every reachability check with zero database connections open, then
   a short write scope. (chosen)
3. Leave `resolve_all()` unchanged, treat the transaction-duration cost as
   accepted debt (as KAN-62's own ticket text originally did for the
   simpler "redundant recheck" version of this cost).

## Decision Outcome

Chosen option: 2, split into a read scope and a write scope. Parallelizing
alone (option 1) reduces wall-clock time but still leaves a database
transaction open for however long the slowest concurrent batch of checks
takes, which does not resolve the idle-in-transaction/lock-retention risk,
only shrinks it. Leaving it unchanged (option 3) was defensible when the
only named cost was redundant network calls across runs; it stopped being
defensible once the cost was understood to be an open database transaction
scaling with unpredictable external I/O, which is a correctness/operability
risk, not only an efficiency one.

### Consequences

1. Good: the database connection's lifetime is now bounded by database
   work (a `SELECT` of staged rows, a batch of upserts), not by network I/O.
2. Good: no port or repository implementation changed, `PostgresConnectionScope`
   already supports sequential re-entry; only `SignalResolver.resolve_all()`'s
   orchestration changed.
3. Bad: `SignalResolver` gives up the "reads and writes share a single
   consistent snapshot" guarantee `ports.py` states as the general rule for
   this port family. The read scope and the write scope are two separate
   transactions now, so a row could change in `silver.hn_postings`/
   `silver.yc_listings` between the read and the write and the batch
   would not see it. The write scope itself is still one transaction (the
   upserts are not individually atomic-then-partial; a failure partway
   through the write scope rolls back every upsert in it, per
   `PostgresConnectionScope.__exit__`'s rollback-on-exception behavior),
   so this is not "some rows written, some not" within one run. The real
   exposure is narrower: a crash in the gap between the two scopes, or
   during the write scope, discards that run's work entirely (nothing
   partial persists), which the next run repeats from scratch.
4. Neutral: this is not a data-integrity loss for this specific orchestrator
   (Decision Driver 2), but it is a real, documented exception to a
   project-wide pattern. A future orchestrator built on the same
   `RepositoryScopePort` family that also needs unbounded external I/O
   inside its per-row work should re-read this ADR rather than assume the
   one-scope rule is unconditional.
5. Neutral: parallelizing the reachability checks themselves (option 1)
   remains open, separate follow-up work; this decision does not preclude
   it, and doing both is likely worthwhile.

## Pros and Cons of the Options

### Option 1: parallelize inside one scope

1. Good: preserves the "no partial batch" guarantee.
2. Good: reuses an already-accepted concurrency pattern (ADR-0003).
3. Bad: the transaction is still open for the duration of the slowest
   concurrent batch of checks, not zero. Idle-in-transaction timeouts and
   lock retention risk remain, just at a smaller magnitude.
4. Bad: does not fix the actual coupling (database transaction lifetime
   depends on external network I/O), only reduces its size.

### Option 2: split into two scopes (chosen)

1. Good: fully decouples the transaction's duration from network I/O.
2. Good: no port/repository code changes needed.
3. Bad: gives up the read/write consistent-snapshot guarantee for this
   orchestrator; the write scope itself remains internally atomic.
4. Bad: a genuine, documented deviation from `ports.py`'s stated
   one-scope-per-orchestrator pattern, needs this ADR so a future reader
   understands it was a deliberate choice, not an oversight.

### Option 3: leave as-is, accepted debt

1. Good: no code change, no risk of introducing a new bug.
2. Bad: the ~33-hour worst case, and the more realistic risk of dozens of
   genuinely dead domains (exactly what this check exists to find) adding
   up to a long-running open transaction, is a real operational risk at
   this project's current stated volume, not a future-scale concern.

## Related

1. `huginn.elt.silver.ports` module docstring: the general one-scope rule
   this ADR documents an exception to.
2. ADR-0003: bounded thread pools for adapter concurrency, the complementary
   optimization (parallelizing the checks) this decision does not preclude.
3. Jira KAN-62 (added the reachability check that created this cost),
   KAN-67 (this decision's ticket).
4. CodeRabbit's review of KAN-62's PR #9: the concrete ~33-hour worst-case
   calculation that raised this from "worth deciding before scale" to
   "worth deciding now."
