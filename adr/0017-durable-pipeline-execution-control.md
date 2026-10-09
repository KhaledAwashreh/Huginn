# 0017: Durable pipeline admission and supervised execution

Status: Accepted
Date: 2026-10-09
Deciders: Khaled Awashreh

## Context and Problem Statement

The approved pipeline-control-and-history design adds administrator-triggered
runs to the existing ADR-0014 stage graph. HTTP lifetime and advisory-lock
availability alone cannot prove that an old executor has stopped after a worker
or connection crash. Gold writes must retain the existing whole-batch scope.

## Decision Drivers

1. Preserve existing ELT source isolation, retries, stage dependencies and stage
   commits without adding a scheduler, arbitrary job engine or matcher stage.
2. Make trigger retries durable and prompt while expensive execution holds a
   separate shared resource.
3. Prevent a new local executor from overlapping old fetch/write threads after
   an advisory-lock connection disappears.
4. Preserve invocation audit and company attribution without private data copies.

## Considered Options

1. Separate durable admission and a supervised executor with a nonexpiring guard.
   (chosen)
2. Treat advisory-lock availability or heartbeat expiry as permission to restart.

## Decision Outcome

Use PostgreSQL idempotent invocation admission with its own short transaction
advisory namespace. Queue claims use row locking; execution requires both a
separate long-lived shared session lock and a durable singleton ownership gate.
The worker and supported full CLI supervise a child process group with a
persisted identity handshake before any ELT stage starts. Managed stage/source
tracking is strict. Missing tracking stops subsequent work; health loss triggers
TERM/KILL/reap, retaining the gate when termination or settlement is uncertain.

The gate never expires automatically. Trusted recovery verifies the exact
stopped host/process-start identity and resource ownership, then atomically
records interruption and clears the matching gate. Completed rows and prior
stage commits remain immutable history. A retry is an explicit new invocation.
Gold company attribution uses the existing batch cursor and persisted upsert UUID,
so Gold and its invocation membership commit or roll back together. Rollback
retains the additive schema and audit data, as documented in the
[pipeline operations runbook](../docs/pipeline-control.md).

### Consequences

1. API acceptance is independent of worker availability and execution locks.
2. A crashed owner can block later work until explicit operator recovery. This
   is the selected safety tradeoff rather than an automatically renewed lease.
3. Existing standalone ingestion/enrichment commands require operator exclusion
   during full runs because their narrower operations remain outside this guard.
4. A future distinct matcher operation may extend the same shared guard additively;
   matcher policy and history remain outside pipeline ownership.
5. The implementation adds no startup DDL, automatic replay, cancellation or
   third-party queue dependency.

## Pros and Cons of the Options

### Durable guard and supervised executor

1. Good: executor termination is established before another local run starts,
   including loss of the lock connection and a crashed supervisor.
2. Bad: an uncertain owner requires trusted operator recovery and can block later
   requests until its process group is stopped.

### Advisory lock or heartbeat expiry alone

1. Good: automatic restart needs less durable control state and operator work.
2. Bad: connection loss can release the lock while old fetch/write threads are
   still alive, allowing overlapping executors and uncertain writes.

## Related

1. [Approved pipeline design](../openspec/changes/pipeline-control-and-history/design.md),
   including the selected safety tradeoff and Gold attribution transaction.
2. [ADR-0014](0014-pipeline-entry-point-and-stage-failure-policy.md), retained stage
   graph and dependency failure behavior.
3. [ADR-0015](0015-management-fastapi-runtime.md), retained synchronous runtime.
4. [Pipeline operations and rollback](../docs/pipeline-control.md).
