## Purpose

Let administrators trigger the existing matchmaking service for a specified user or a captured set of eligible users, follow durable progress, and inspect acknowledged outcomes.

## ADDED Requirements

### Requirement: Authoritative administrator access
Target-user search, trigger, run history, detail, and per-user results SHALL require an authenticated active administrator, enforced on every request. Unauthenticated requests SHALL receive generic 401 and ordinary users generic 403. Triggers SHALL require session-bound CSRF. Operational responses SHALL be private and non-cacheable; public signup/profile requests SHALL not grant administrator privileges.

#### Scenario: Administrator demoted with page open
- **WHEN** a signed-in administrator is demoted
- **THEN** further operational requests are forbidden and the browser stops controls/polling and clears administrator query data.

### Requirement: Explicit targets and signal window
Each trigger SHALL name one user or all eligible users and an inclusive timezone-aware signal window. All-eligible SHALL mean users whose accounts are active and who have at least one active strategy at acceptance. The accepted run SHALL persist exact target IDs and one resolved window; later user/strategy changes SHALL not silently add targets. A single-user request SHALL require an existing active account but SHALL permit no active strategies, reporting that condition through the result. Invalid input and an empty all-eligible selection SHALL be rejected before execution. Target search SHALL be bounded and SHALL expose only identity fields needed by administrators, never passwords, recovery identities, session data, or criteria.

#### Scenario: Target population changes while queued
- **WHEN** another eligible user is created after a run is accepted
- **THEN** that user is absent from the accepted run's target set and denominator, and existing targets are rechecked by the service at execution.

#### Scenario: Selected user becomes disabled
- **WHEN** an accepted target's account is disabled before its evaluation
- **THEN** the existing service reports it skipped as disabled without creating matches, and that target outcome is visible.

### Requirement: Durable trigger identity and bounded execution
The trigger SHALL persist a queued run before returning 202 with its identity, resolved window, and target count. The same administrator/client request ID with identical validated input SHALL resolve to the existing run; changed input with that ID SHALL receive a conflict. At most one queued/running managed matchmaking run SHALL exist. Execution SHALL occur outside the HTTP request, using the existing matchmaking service rather than a separate evaluator. Collection and matchmaking SHALL not execute concurrently through supported full CLI/managed entrypoints. A queued run waiting for the worker or collection guard SHALL remain visibly queued.

#### Scenario: Lost trigger response
- **WHEN** an administrator explicitly repeats the same request after its receipt is lost
- **THEN** the existing run is returned without adding another run or changing its captured targets/window.

#### Scenario: Collection is running
- **WHEN** an accepted matchmaking run is waiting while full collection holds the shared guard
- **THEN** it remains queued and no user evaluation starts until the guard can be safely acquired.

#### Scenario: Operator CLI cannot acquire execution admission
- **WHEN** the supported matchmaking CLI finds a busy or unavailable shared guard before execution
- **THEN** it starts no user evaluation and returns a sanitized execution error with a nonzero exit; successful batch output remains compatible.

### Requirement: Preserve creation-only matching semantics
Execution SHALL retain existing active-strategy selection, industry/size/country criteria, exclusions, signal-window qualification, per-user transactions, duplicate protection, and bounded transaction retries. Existing match status and notes SHALL remain unchanged. No trigger SHALL perform scoring, ranking, digest delivery, resurfacing, automatic collection, or automatic re-evaluation of old matches. One user failure SHALL not prevent remaining users from being attempted when execution and durable tracking remain healthy.

#### Scenario: Same company qualifies through multiple strategies
- **WHEN** multiple active strategies qualify the same company for one user
- **THEN** that user has one company match and existing match status/notes are preserved on later explicit runs.

### Requirement: Honest durable progress and per-user results
Run detail SHALL show the immutable target count, settled-target count, current user when known, requested/start/finish times, heartbeat freshness, and state. User progress SHALL be based on settled targets, including explicitly identified skipped/failed/uncertain targets; it SHALL not claim a percentage of company scans or success because all attempts are settled. Per-user results SHALL distinguish acknowledged success, disabled/missing user, execution failure, unknown commit outcome, and work not executed. Acknowledged success SHALL report strategies evaluated/skipped, unique candidates, created-match count, existing-match count, and bounded skipped-strategy reason pages. Unknown counts SHALL remain unknown and SHALL not contribute fabricated values to aggregate totals.

#### Scenario: User evaluation succeeds with incomplete ICP
- **WHEN** the service skips a strategy as incomplete and creates no matches
- **THEN** results show that skipped reason and known counts rather than presenting the user as a successful positive match or hiding configuration issues.

#### Scenario: Every target is settled with one failure
- **WHEN** all targets have outcomes but one failed or has an uncertain commit
- **THEN** the progress bar can be full while the run clearly reports partial failure or uncertainty, never overall success.

### Requirement: Interruption and uncertain outcome
Started user evaluations SHALL not be automatically replayed following worker loss. Stale heartbeat SHALL indicate stale tracking, not prove completion or failure. A service's unknown commit SHALL remain unknown and SHALL not automatically retry that user. If execution or result bookkeeping is lost after a user starts, that user SHALL remain uncertain, acknowledged earlier results SHALL remain intact, and pending users SHALL remain not executed until safe stopped-executor reconciliation. New execution SHALL not be admitted while the prior executor may still run. A deliberate subsequent run SHALL use a new run identity and rely on existing match deduplication.

#### Scenario: Result persistence fails after matcher commit
- **WHEN** the matcher may have committed but its result cannot be durably acknowledged
- **THEN** the system does not claim zero matches, does not replay the evaluation, and retains an uncertain record requiring explicit recovery.

#### Scenario: Standalone matcher CLI executor is interrupted
- **WHEN** an operator proves that the exact standalone matching executor stopped and reconciles its execution identity
- **THEN** its matching-owned guard can be cleared without creating fictitious managed-run results or clearing a pipeline-owned guard.

### Requirement: Administrator browser workflows
The administrator Matchmaking area SHALL offer searchable single-user or all-eligible targeting, visible signal-window controls, and manual Run matchmaking. It SHALL display the server-accepted target count/window, paginated run history and per-user result pages, safe skipped-strategy reasons, and links to supported run detail. It SHALL prevent duplicate clicks, retain a request ID across uncertainty, and poll only visible queued/running views with bounded intervals. Navigation, terminal state, hidden page, 401, or 403 SHALL stop polling as applicable. Keyboard, focus, contrast, and narrow layouts SHALL follow shared foundation standards.

#### Scenario: Browser closes after acceptance
- **WHEN** an administrator closes the browser after a run is accepted
- **THEN** background work continues independently and reopening its run URL reads the persisted state.

### Requirement: Private ownership boundary for user results
The separate Matches capability SHALL be able to read a user's latest own durable evaluation through an owner-scoped projection without granting administrator operational access. That projection SHALL exclude other targets, requester details, run-wide totals, criteria, and operational errors. Current strategy presence SHALL not be claimed to be a historical strategy snapshot.

#### Scenario: Ordinary user requests operational run details
- **WHEN** an ordinary user knows a run ID containing their evaluation
- **THEN** the administrator detail endpoint still returns 403 while the owner projection can expose only their own safe outcome.

### Requirement: Existing data and tooling remain preserved
Deployment SHALL use additive migrations and explicit operator setup, preserving existing accounts, sessions, configuration, Gold data, and match records. Startup SHALL not migrate, seed, reset data, assign an administrator automatically, or run collection/matching. Implementation SHALL use shared schema/type/UI/layer standards and meaningful regression checks with disposable PostgreSQL 16; no new job infrastructure or runtime dependence on frontend tooling SHALL be required for API/worker startup.

#### Scenario: Upgrade an existing installation
- **WHEN** the approved migrations are applied to a populated installation
- **THEN** existing matches and configuration remain unchanged and no run starts until an authorized explicit trigger or CLI invocation.
