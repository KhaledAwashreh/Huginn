# Management API CRUD implementation handoff

## What changed

The `management-api-crud` OpenSpec change now contains the proposal, six
capability specifications, technical design, and dependency-ordered task list
for KAN-72 through KAN-78. No application code has been implemented.

## Why it matters

The artifacts define one coherent path from the operational database through
psycopg repositories and application services to authenticated Flask APIs.
They resolve the Account/User/Profile aggregate, session ownership, CRUD
boundaries, and the previously ambiguous ICP combination behavior before code
is written.

## Current status

- Planning is complete and `openspec validate management-api-crud --strict`
  passes as of 2026-10-02.
- Implementation is ready to start at task 1.1.
- The current checkout also contains unrelated user-owned files and a
  one-line modification in `src/huginn/ops/postgres_job_run_writer.py`. Preserve
  them and do not include them in this feature.
- Confidence: high for repository state and documented design. Application
  behavior is unverified because implementation has not started.

## Setup

- Repository: `/home/kawashreh/Projects/Huginn`
- Change: `openspec/changes/management-api-crud`
- Runtime: Python 3.14, Flask 3, Pydantic 2, psycopg 3, PostgreSQL 16
- Instruction: prefix every shell command with `rtk`.
- Prerequisite: use a dedicated feature worktree and a disposable management
  database. Do not reset an existing or shared database.

## How to implement and verify

- Use the OpenSpec apply workflow and execute `tasks.md` in order.
- Use a Sol medium agent as orchestrator, Luna agents for narrow implementation
  groups, and a fresh-context Sol high agent for final local code review.
- The orchestrator owns all integration decisions, inspects shared-worktree
  diffs after each delegation, and reruns every stated verification.
- The final gate is Python 3.14 compile, Ruff, full pytest, live PostgreSQL 16
  integration tests, strict OpenSpec validation, and clear Sol high review.
- Commit only after review findings are resolved and the full gate passes. Do
  not push or open a pull request without separate authorization.

## Critical behavior

- Account, User, and empty ProfessionalProfile provision atomically.
- Passwords use Werkzeug scrypt with built-in random salts. Raw passwords are
  not normalized, logged, returned, or accepted on command lines.
- Authentication uses opaque database-backed sessions, digest-only storage,
  expiry/revocation, HttpOnly cookies, and a session-bound CSRF header.
- All resource ownership comes from the authenticated User. Cross-owner
  resources appear not found.
- ICP values use OR within industries, sizes, and geographies, then AND across
  those dimensions. Every selected value can combine with every selected value
  in the other dimensions.
- If any positive ICP list is empty, evaluation returns no results before a
  candidate query. Exclusions are global vetoes.
- Profile collections use the existing repository schemas, not the conflicting
  older KAN-74 draft.

## Main documents

- `proposal.md`: scope and capability map
- `design.md`: implementation decisions and trade-offs
- `specs/*/spec.md`: normative requirements and scenarios
- `tasks.md`: executable implementation sequence and verification
- `adr/0011-management-api-foundation.md`: existing foundation decision
- `docs/management-foundation.md`: current runtime and bootstrap behavior

## Next steps

1. Start with task 1.1 and record the clean baseline.
2. Reconcile KAN-76 wording with the accepted empty-positive-list behavior.
3. Implement one dependency group at a time under the defined agent roles.
4. Stop for user input only if implementation evidence forces a product or
   scope decision not resolved by the artifacts.
