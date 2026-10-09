BEGIN;

CREATE TABLE IF NOT EXISTS ops.pipeline_invocations (
    id UUID PRIMARY KEY,
    requester_account_id UUID NOT NULL REFERENCES operational.accounts(id) ON DELETE RESTRICT,
    request_id UUID NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
    requested_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    plan JSONB NOT NULL,
    worker_id TEXT,
    heartbeat_at TIMESTAMPTZ,
    safe_error_code TEXT,
    company_results_tracking_state TEXT NOT NULL DEFAULT 'unknown_legacy'
        CHECK (company_results_tracking_state IN ('tracked', 'unknown_legacy')),
    UNIQUE (requester_account_id, request_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS pipeline_invocations_one_active
    ON ops.pipeline_invocations ((true))
    WHERE state IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS pipeline_invocations_history
    ON ops.pipeline_invocations (requested_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS ops.pipeline_invocation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invocation_id UUID NOT NULL REFERENCES ops.pipeline_invocations(id) ON DELETE RESTRICT,
    sequence BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    kind TEXT NOT NULL,
    transition_key TEXT NOT NULL,
    stage_name TEXT,
    source_name TEXT,
    safe_code TEXT,
    safe_message TEXT,
    metrics JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (invocation_id, sequence),
    UNIQUE (invocation_id, transition_key)
);

CREATE TABLE IF NOT EXISTS ops.pipeline_trigger_throttle (
    requester_account_id UUID NOT NULL REFERENCES operational.accounts(id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (requester_account_id, request_id)
);
CREATE INDEX IF NOT EXISTS pipeline_trigger_throttle_window
    ON ops.pipeline_trigger_throttle (requester_account_id, requested_at);

CREATE TABLE IF NOT EXISTS ops.pipeline_execution_guard (
    singleton SMALLINT PRIMARY KEY DEFAULT 1 CHECK (singleton = 1),
    owner_id UUID,
    execution_id UUID,
    invocation_id UUID REFERENCES ops.pipeline_invocations(id) ON DELETE RESTRICT,
    host TEXT,
    supervisor_pid INTEGER,
    supervisor_started_at TEXT,
    executor_pid INTEGER,
    executor_started_at TEXT,
    acquired_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (NOT active OR (owner_id IS NOT NULL AND execution_id IS NOT NULL AND host IS NOT NULL AND supervisor_pid IS NOT NULL AND supervisor_started_at IS NOT NULL AND acquired_at IS NOT NULL))
);
INSERT INTO ops.pipeline_execution_guard (singleton, active)
VALUES (1, FALSE) ON CONFLICT (singleton) DO NOTHING;

ALTER TABLE ops.job_runs
    ADD COLUMN IF NOT EXISTS invocation_id UUID REFERENCES ops.pipeline_invocations(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS parent_job_run_id UUID REFERENCES ops.job_runs(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS execution_kind TEXT CHECK (execution_kind IS NULL OR execution_kind IN ('stage', 'source'));
CREATE UNIQUE INDEX IF NOT EXISTS job_runs_invocation_id_id_key
    ON ops.job_runs (invocation_id, id);
CREATE INDEX IF NOT EXISTS job_runs_invocation_parent
    ON ops.job_runs (invocation_id, parent_job_run_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'job_runs_parent_same_invocation_fk'
          AND conrelid = 'ops.job_runs'::regclass
    ) THEN
        ALTER TABLE ops.job_runs
            ADD CONSTRAINT job_runs_parent_same_invocation_fk
            FOREIGN KEY (invocation_id, parent_job_run_id)
            REFERENCES ops.job_runs (invocation_id, id) ON DELETE RESTRICT;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS ops.pipeline_company_results (
    invocation_id UUID NOT NULL REFERENCES ops.pipeline_invocations(id) ON DELETE RESTRICT,
    company_id UUID NOT NULL REFERENCES gold.company(id) ON DELETE RESTRICT,
    stage_job_run_id UUID NOT NULL,
    PRIMARY KEY (invocation_id, company_id),
    FOREIGN KEY (invocation_id, stage_job_run_id)
        REFERENCES ops.job_runs (invocation_id, id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS pipeline_company_results_page
    ON ops.pipeline_company_results (invocation_id, company_id);

COMMIT;
