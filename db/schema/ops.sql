-- Ops schema: pipeline-run metadata, not business data. See architecture
-- document sections 3 and 5, which name cron plus a `job_runs` table as
-- the orchestration mechanism, and Jira KAN-27.
--
-- Kept out of bronze/silver/gold/operational: those hold ingested or
-- domain data, this holds metadata about the pipeline's own runs. No
-- foreign keys into or out of this schema; `id` doubles as the run ID
-- already threaded through `RawStorePort.write` and `bronze.*.run_id`
-- (section 4.1), a plain UUID value rather than an enforced reference,
-- since bronze rows are written before the run is known to have
-- succeeded. Wiring `IngestionService` to write a row per source per run
-- is Jira KAN-28's job, not this file's.

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE ops.job_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed')),
    rows_written INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
