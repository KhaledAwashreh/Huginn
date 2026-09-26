-- Add 'skipped' to ops.job_runs.status, for adr/0014's dependency-aware
-- skip-on-failure policy: src/huginn/elt/__main__.py's pipeline entrypoint
-- marks a stage SKIPPED, not FAILED, when a stage it depends on did not
-- succeed. FAILED stays reserved for a stage that actually ran and raised.
--
-- Drop-then-add, because Postgres has no ADD CONSTRAINT IF NOT EXISTS and
-- this file must be safely re-runnable. The original inline CHECK in
-- db/schema/ops.sql has no explicit constraint name, so Postgres
-- auto-generated job_runs_status_check (table name + column name +
-- "_check"); db/schema/ops.sql now names it explicitly for the same reason
-- gold-company-scale.sql does: so a database that ran this file already
-- converges on one name instead of accumulating a duplicate pair.
--
-- Idempotent.

ALTER TABLE ops.job_runs
    DROP CONSTRAINT IF EXISTS job_runs_status_check;

ALTER TABLE ops.job_runs
    ADD CONSTRAINT job_runs_status_check
    CHECK (status IN ('running', 'succeeded', 'failed', 'skipped'));
