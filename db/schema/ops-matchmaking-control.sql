BEGIN;

CREATE TABLE IF NOT EXISTS ops.matchmaking_runs (
    id UUID PRIMARY KEY,
    requester_account_id UUID NOT NULL REFERENCES operational.accounts(id) ON DELETE RESTRICT,
    request_id UUID NOT NULL,
    canonical_request JSONB NOT NULL,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('user', 'all_eligible')),
    cutoff TIMESTAMPTZ NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'completed_with_errors', 'interrupted')),
    requested_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    worker_id TEXT,
    heartbeat_at TIMESTAMPTZ,
    target_count INTEGER NOT NULL CHECK (target_count > 0),
    settled_target_count INTEGER NOT NULL DEFAULT 0 CHECK (settled_target_count BETWEEN 0 AND target_count),
    safe_error_code TEXT,
    UNIQUE (requester_account_id, request_id),
    CHECK (cutoff <= as_of),
    CHECK ((state IN ('queued', 'running')) = (finished_at IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS matchmaking_runs_one_active
    ON ops.matchmaking_runs ((true)) WHERE state IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS matchmaking_runs_history
    ON ops.matchmaking_runs (requested_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS ops.matchmaking_run_users (
    run_id UUID NOT NULL REFERENCES ops.matchmaking_runs(id) ON DELETE RESTRICT,
    user_id UUID NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    state TEXT NOT NULL CHECK (state IN ('pending', 'running', 'succeeded', 'disabled_user', 'user_not_found', 'failed', 'commit_outcome_unknown', 'not_executed')),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    strategies_evaluated INTEGER CHECK (strategies_evaluated >= 0),
    strategies_skipped INTEGER CHECK (strategies_skipped >= 0),
    unique_candidates_count INTEGER CHECK (unique_candidates_count >= 0),
    created_matches_count INTEGER CHECK (created_matches_count >= 0),
    existing_matches_skipped_count INTEGER CHECK (existing_matches_skipped_count >= 0),
    safe_reason TEXT CHECK (safe_reason IS NULL OR safe_reason IN (
        'database_unavailable', 'database_failure', 'retries_exhausted',
        'commit_outcome_unknown', 'disabled_user', 'user_not_found', 'executor_interrupted',
        'execution_failed', 'result_tracking_uncertain'
    )),
    PRIMARY KEY (run_id, user_id),
    UNIQUE (run_id, ordinal),
    CHECK ((state IN ('pending', 'running')) = (finished_at IS NULL)),
    CHECK (
        (state = 'succeeded' AND strategies_evaluated IS NOT NULL AND strategies_skipped IS NOT NULL
            AND unique_candidates_count IS NOT NULL AND created_matches_count IS NOT NULL
            AND existing_matches_skipped_count IS NOT NULL)
        OR (state <> 'succeeded' AND strategies_evaluated IS NULL AND strategies_skipped IS NULL
            AND unique_candidates_count IS NULL AND created_matches_count IS NULL
            AND existing_matches_skipped_count IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS matchmaking_run_users_page
    ON ops.matchmaking_run_users (run_id, ordinal);
CREATE INDEX IF NOT EXISTS matchmaking_run_users_user_latest
    ON ops.matchmaking_run_users (user_id, run_id);

CREATE TABLE IF NOT EXISTS ops.matchmaking_run_skipped_strategies (
    run_id UUID NOT NULL,
    user_id UUID NOT NULL,
    strategy_id UUID NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('invalid_icp', 'incomplete_icp', 'unsupported_region')),
    PRIMARY KEY (run_id, user_id, strategy_id),
    FOREIGN KEY (run_id, user_id) REFERENCES ops.matchmaking_run_users(run_id, user_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS matchmaking_run_skipped_strategies_page
    ON ops.matchmaking_run_skipped_strategies (run_id, user_id, strategy_id);

CREATE TABLE IF NOT EXISTS ops.matchmaking_trigger_throttle (
    requester_account_id UUID NOT NULL REFERENCES operational.accounts(id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (requester_account_id, request_id)
);
CREATE INDEX IF NOT EXISTS matchmaking_trigger_throttle_window
    ON ops.matchmaking_trigger_throttle (requester_account_id, requested_at);

ALTER TABLE ops.pipeline_execution_guard
    ADD COLUMN IF NOT EXISTS resource_kind TEXT NOT NULL DEFAULT 'pipeline',
    ADD COLUMN IF NOT EXISTS matchmaking_run_id UUID REFERENCES ops.matchmaking_runs(id) ON DELETE RESTRICT;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pipeline_execution_guard_resource_kind_check') THEN
        ALTER TABLE ops.pipeline_execution_guard ADD CONSTRAINT pipeline_execution_guard_resource_kind_check
            CHECK (resource_kind IN ('pipeline', 'matchmaking'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pipeline_execution_guard_resource_reference_check') THEN
        ALTER TABLE ops.pipeline_execution_guard ADD CONSTRAINT pipeline_execution_guard_resource_reference_check
            CHECK (
                (resource_kind = 'pipeline' AND matchmaking_run_id IS NULL)
                OR (resource_kind = 'matchmaking' AND invocation_id IS NULL)
            );
    END IF;
END
$$;

COMMIT;
