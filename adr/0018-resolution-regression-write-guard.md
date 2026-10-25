# 0018: Guard source identity regressions before resolution writes

Status: Proposed
Date: 2026-10-25
Deciders: Pending maintainer review

## Context and Problem Statement

A real source refresh processed 5,418 records and reported success while
changing 4,152 of 4,590 previously domain-normalized identities in its input
cohort to unresolved. The normal writer then generated thousands of pending
review entries. Subsequent live probes resolved most affected domains.
The precise earlier DNS or HTTP failure is unconfirmed.

KAN-62 intentionally converts failed reachability checks to unresolved.
ADR-0014 consequently assumes those row-level results are safe to persist.
That behavior remains useful for individual rows, but a successful row count
does not establish that a large batch is safe to write.

## Decision Drivers

1. Preserve existing identities, Gold data and review work during a widespread
   failure, while retaining independently committed Bronze and staging facts.
2. Keep network I/O outside database scopes as required by ADR-0006.
3. Use the existing failed/skipped stage semantics without a schema change.
4. Do not infer withdrawal from an omitted source record, or treat a valid
   domain-to-domain change as lost resolution.
5. Avoid hiding a smaller source's outage behind a healthy larger source.

## Considered Options

1. Check per-source identity regressions before the atomic write (chosen).
2. Keep boolean reachability and unconditional writes unchanged.
3. Introduce persisted reachable/unreachable/indeterminate outcomes and new
   per-row retry, freshness and deferred-write behavior in this effort.
4. Check only the aggregate resolved count across all sources.

## Decision Outcome

Proposed option: 1. Within the write transaction, lock existing
DOMAIN_NORMALIZED rows for the exact proposed source/stable-ID pairs.
For each source, count the previous positive cohort and how many candidates
would lose DOMAIN_NORMALIZED. If the loss exceeds 10%, raise before any
resolution upsert. Exactly 10% remains permitted. Valid domain changes do
not count; previous rows outside the batch are excluded.

The pure guard returns aggregate counts for accepted batches. Rejections
identify the source and source-specific counts without listing domains,
raw payloads or credentials. The existing stage runner records FAILED and
skips manual review and Gold dependencies. Its normal command outcome must
remain unsuccessful rather than reporting a successful destructive refresh.

The proposed 10% limit is an operational review boundary, not a statistical
network-health classifier. Real preserved replay showed 90.46% loss in the
bad mixed-source batch and 100% in its EU cohort. Healthy whole-batch
comparisons stayed below 1%; EU healthy comparisons lost 0.88% or less.
The healthy October 24 to October 25 comparison lost 0.15% overall and no
EU identities. These observations justify a conservative first boundary;
they do not establish a universal expected churn rate.

### Consequences

1. Good: a blocked batch makes zero resolution writes. Gold and pending review
   dependencies do not run, and previously committed source facts remain.
2. Good: a source outage cannot be diluted by positives from another source.
3. Good: existing DNS safety, bounded retries, HEAD/GET fallback and redirect
   handling remain unchanged. No automatic weakening or bypass is added.
4. Bad: a legitimate large loss requires investigation before retrying.
   Repeating the same batch does not automatically approve it.
5. Bad: small source cohorts are sensitive to a single loss. A one-row
   positive cohort losing its identity exceeds the limit.
6. Limited: this guard protects existing cohorts. It cannot recognize a first
   batch with no prior identities, and individual transient failures below
   the threshold retain KAN-62 behavior and can accumulate across runs.
7. Limited: prior-positive row locks assume normal pipeline execution
   serialization. They do not serialize arbitrary writers promoting keys
   that were absent or unresolved at the guard read. Legacy explicit EU
   enrichment execution remains outside that existing execution guard.
8. Limited: this implementation is proposed for review and is not a deployment
   or a fresh-data write to the persistent database.

## Pros and Cons of the Options

### Option 1: Per-source pre-write guard

1. Good: addresses the observed destructive batch without changing identity
   eligibility or introducing new persisted lifecycle semantics.
2. Bad: the review boundary needs deliberate operator judgment for legitimate
   bulk changes; it does not identify the exact transport failure.

### Option 2: Unconditional boolean-result writes

1. Good: existing behavior and no additional reads.
2. Bad: the recorded failure can recur while still reporting success.

### Option 3: Persisted reachability outcomes

1. Good: can distinguish temporary uncertainty from identity decisions.
2. Bad: requires a wider contract across resolution, deferred records, stage
   outcomes and guarded source evidence. It remains a separate follow-up.

### Option 4: Aggregate-only guard

1. Good: small implementation and easy summary.
2. Bad: a complete EU outage can remain below the aggregate threshold when
   YC succeeds, preserving the same failure for smaller sources.

## Related

1. Architecture document sections 4.2, 5 and 6.
2. ADR-0006: split signal-resolver scope for network I/O.
3. ADR-0014: dependency-aware stage failure behavior.
4. KAN-62: existing domain reachability policy and its accepted limitations.
5. Live-data incident and replay evidence from the authorized operational run
   on October 24-25, 2026. Raw records, backups and review artifacts remain
   local and ignored.
