# 0003: Bounded thread pools for adapter concurrency, not asyncio

Status: Accepted
Date: 2026-09-08
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting)

## Context and Problem Statement

Every source adapter's `fetch()` needs bounded concurrent HTTP requests: KAN-29's HN adapter fetches a root thread's top-level comments concurrently, and KAN-30's YC adapter will issue several per-batch Algolia queries concurrently. `BEST_PRACTICES.md` flagged the choice between `asyncio` and threading as an open, project-wide decision, first closed ad hoc for KAN-29's implementation plan alone. Left unresolved at the project level, each future adapter would re-litigate the same question, or worse, silently pick different mechanisms.

## Decision Drivers

1. `requests`, the project's only HTTP dependency, is synchronous. Calling it from inside an `async def` function blocks the entire event loop, which defeats the purpose of `asyncio`.
2. No code anywhere in the project uses `async`/`await` today. Introducing `asyncio` for adapter fetches alone would mean maintaining two concurrency models side by side for no shared benefit.
3. The actual concurrency need is modest: a small bounded cap (5-10 in flight), not thousands of simultaneous connections. Threads handle this scale without measurable overhead.
4. `concurrent.futures.ThreadPoolExecutor` is standard library. An `asyncio` approach would require adding `httpx` or another async-capable HTTP client as a new dependency.

## Considered Options

1. `asyncio` with an async-compatible HTTP client (e.g. `httpx`)
2. `concurrent.futures.ThreadPoolExecutor` with the existing `requests` dependency (chosen)

## Decision Outcome

Chosen option: 2, `ThreadPoolExecutor`. Zero new dependencies, matches the synchronous HTTP library already in use throughout the project, and meets every adapter's bounded-concurrency requirement at the scale this project actually operates at. This is now the standing default for any I/O-bound concurrent work, not a per-ticket decision each adapter re-makes.

### Consequences

1. Good: no new dependency added to `pyproject.toml`.
2. Good: one concurrency model project-wide; a contributor reading any adapter sees the same pattern.
3. Bad: if a future workload needs concurrency at a much larger scale (hundreds or thousands of simultaneous requests), threads carry more per-unit overhead than coroutines. Revisit this ADR if that ever becomes real, not before.
4. Neutral: every adapter must still explicitly bound its own pool size (`max_workers`); nothing about this choice makes an unbounded pool structurally impossible, that discipline still has to be applied per adapter (see `BEST_PRACTICES.md` section 9, point 3).

## Pros and Cons of the Options

### Option 1: asyncio + httpx

1. Good: coroutines have lower per-unit overhead than threads at very high concurrency counts.
2. Good: `asyncio` is the more idiomatic modern-Python answer for I/O-bound work in general.
3. Bad: requires swapping or supplementing `requests` with an async-capable client, a new dependency.
4. Bad: introduces a second concurrency model into a codebase that otherwise has none, raising the bar for anyone touching adapter code.

### Option 2: ThreadPoolExecutor (chosen)

1. Good: stdlib only, no new dependency.
2. Good: consistent with the one synchronous HTTP client already in use.
3. Good: `with ThreadPoolExecutor(...) as executor:` guarantees `shutdown(wait=True)` runs even on a worker exception, so no leaked threads on the failure path (confirmed in KAN-29's implementation and its final review).
4. Bad: does not scale as cleanly to very large concurrency counts, not a concern at this project's actual scale.

## Related

1. `architecture-notes/hn-fetch-plan.md` section 2: the original per-ticket ruling for KAN-29 that this ADR generalizes.
2. `docs/superpowers/plans/2026-09-07-kan-29-hn-adapter.md`, Global Constraint 8: the first concrete application of this decision.
3. `CLAUDE.md` code standard 8, `BEST_PRACTICES.md` section 9: pointers to this ADR rather than restating its reasoning.
4. Jira KAN-29 (first adapter built against this), KAN-30 (next adapter to apply it).
