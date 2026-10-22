-- Additive, idempotent schema for versioned source context. This deliberately
-- does not change the existing current-state staging tables.
BEGIN;
CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.source_context_snapshot (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    source_url TEXT,
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    parser_version TEXT NOT NULL,
    normalized_text TEXT,
    header_start INTEGER,
    header_end INTEGER,
    body_start INTEGER,
    body_end INTEGER,
    source_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_times JSONB NOT NULL DEFAULT '{}'::jsonb,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT source_context_snapshot_pkey PRIMARY KEY (id),
    CONSTRAINT source_context_snapshot_source_ck CHECK
        (source IN ('hn', 'eu_startups', 'yc')),
    CONSTRAINT source_context_snapshot_payload_sha256_ck CHECK
        (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT source_context_snapshot_header_span_ck CHECK (
        (header_start IS NULL AND header_end IS NULL)
        OR (header_start >= 0 AND header_end >= header_start)
    ),
    CONSTRAINT source_context_snapshot_body_span_ck CHECK (
        (body_start IS NULL AND body_end IS NULL)
        OR (body_start >= 0 AND body_end >= body_start)
    ),
    CONSTRAINT source_context_snapshot_version_uq UNIQUE
        (source, stable_id, payload_sha256, parser_version)
);

CREATE TABLE IF NOT EXISTS silver.source_context_run (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    mode TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    total_inputs INTEGER NOT NULL DEFAULT 0,
    captured_count INTEGER NOT NULL DEFAULT 0,
    excluded_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    run_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT source_context_run_pkey PRIMARY KEY (id),
    CONSTRAINT source_context_run_source_ck CHECK
        (source IN ('hn', 'eu_startups', 'yc')),
    CONSTRAINT source_context_run_mode_ck CHECK (mode IN ('capture')),
    CONSTRAINT source_context_run_fingerprint_ck CHECK
        (input_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT source_context_run_status_ck CHECK
        (status IN ('running', 'complete', 'partial', 'failed', 'interrupted')),
    CONSTRAINT source_context_run_total_ck CHECK (total_inputs >= 0),
    CONSTRAINT source_context_run_captured_ck CHECK (captured_count >= 0),
    CONSTRAINT source_context_run_excluded_ck CHECK (excluded_count >= 0),
    CONSTRAINT source_context_run_failed_ck CHECK (failed_count >= 0),
    CONSTRAINT source_context_run_counts_ck CHECK (
        captured_count + excluded_count + failed_count <= total_inputs
    )
);

CREATE TABLE IF NOT EXISTS silver.source_context_outcome (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    snapshot_id UUID,
    observation_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT source_context_outcome_pkey PRIMARY KEY (id),
    CONSTRAINT source_context_outcome_run_fkey FOREIGN KEY (run_id)
        REFERENCES silver.source_context_run (id) ON DELETE CASCADE,
    CONSTRAINT source_context_outcome_source_ck CHECK
        (source IN ('hn', 'eu_startups', 'yc')),
    CONSTRAINT source_context_outcome_payload_sha256_ck CHECK
        (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT source_context_outcome_status_ck CHECK
        (status IN ('captured', 'excluded', 'failed')),
    CONSTRAINT source_context_outcome_snapshot_fkey FOREIGN KEY (snapshot_id)
        REFERENCES silver.source_context_snapshot (id),
    CONSTRAINT source_context_outcome_snapshot_ck CHECK (
        (status = 'captured' AND snapshot_id IS NOT NULL)
        OR (status <> 'captured' AND snapshot_id IS NULL)
    ),
    CONSTRAINT source_context_outcome_run_record_uq UNIQUE (run_id, source, stable_id)
);

CREATE INDEX IF NOT EXISTS source_context_snapshot_source_stable_idx
    ON silver.source_context_snapshot (source, stable_id);
CREATE INDEX IF NOT EXISTS source_context_outcome_run_idx
    ON silver.source_context_outcome (run_id, status);

-- CREATE TABLE IF NOT EXISTS alone can silently accept an incompatible table.
-- Verify required column types/nullability and named constraints on reruns.
DO $$
DECLARE
    expected RECORD;
    actual_type TEXT;
    actual_nullable TEXT;
BEGIN
    FOR expected IN
        SELECT * FROM (VALUES
            ('source_context_snapshot', 'id', 'uuid', 'NO'),
            ('source_context_snapshot', 'source', 'text', 'NO'),
            ('source_context_snapshot', 'stable_id', 'text', 'NO'),
            ('source_context_snapshot', 'source_url', 'text', 'YES'),
            ('source_context_snapshot', 'payload_sha256', 'text', 'NO'),
            ('source_context_snapshot', 'parser_version', 'text', 'NO'),
            ('source_context_snapshot', 'normalized_text', 'text', 'YES'),
            ('source_context_snapshot', 'header_start', 'integer', 'YES'),
            ('source_context_snapshot', 'header_end', 'integer', 'YES'),
            ('source_context_snapshot', 'body_start', 'integer', 'YES'),
            ('source_context_snapshot', 'body_end', 'integer', 'YES'),
            ('source_context_snapshot', 'source_fields', 'jsonb', 'NO'),
            ('source_context_snapshot', 'source_times', 'jsonb', 'NO'),
            ('source_context_snapshot', 'captured_at', 'timestamp with time zone', 'NO'),
            ('source_context_run', 'id', 'uuid', 'NO'),
            ('source_context_run', 'source', 'text', 'NO'),
            ('source_context_run', 'mode', 'text', 'NO'),
            ('source_context_run', 'parser_version', 'text', 'NO'),
            ('source_context_run', 'input_fingerprint', 'text', 'NO'),
            ('source_context_run', 'status', 'text', 'NO'),
            ('source_context_run', 'total_inputs', 'integer', 'NO'),
            ('source_context_run', 'captured_count', 'integer', 'NO'),
            ('source_context_run', 'excluded_count', 'integer', 'NO'),
            ('source_context_run', 'failed_count', 'integer', 'NO'),
            ('source_context_run', 'started_at', 'timestamp with time zone', 'NO'),
            ('source_context_run', 'finished_at', 'timestamp with time zone', 'YES'),
            ('source_context_run', 'run_metadata', 'jsonb', 'NO'),
            ('source_context_outcome', 'id', 'uuid', 'NO'),
            ('source_context_outcome', 'run_id', 'uuid', 'NO'),
            ('source_context_outcome', 'source', 'text', 'NO'),
            ('source_context_outcome', 'stable_id', 'text', 'NO'),
            ('source_context_outcome', 'payload_sha256', 'text', 'NO'),
            ('source_context_outcome', 'status', 'text', 'NO'),
            ('source_context_outcome', 'reason', 'text', 'YES'),
            ('source_context_outcome', 'snapshot_id', 'uuid', 'YES'),
            ('source_context_outcome', 'observation_metadata', 'jsonb', 'NO'),
            ('source_context_outcome', 'recorded_at', 'timestamp with time zone', 'NO')
        ) AS columns(table_name, column_name, data_type, is_nullable)
    LOOP
        SELECT data_type, is_nullable INTO actual_type, actual_nullable
        FROM information_schema.columns
        WHERE table_schema = 'silver'
          AND table_name = expected.table_name
          AND column_name = expected.column_name;
        IF NOT FOUND OR actual_type <> expected.data_type
           OR actual_nullable <> expected.is_nullable THEN
            RAISE EXCEPTION 'incompatible silver.%.% shape',
                expected.table_name, expected.column_name;
        END IF;
    END LOOP;

    FOR expected IN
        SELECT * FROM (VALUES
            ('source_context_snapshot', 'source_context_snapshot_pkey', 'p'),
            ('source_context_snapshot', 'source_context_snapshot_source_ck', 'c'),
            ('source_context_snapshot', 'source_context_snapshot_payload_sha256_ck', 'c'),
            ('source_context_snapshot', 'source_context_snapshot_header_span_ck', 'c'),
            ('source_context_snapshot', 'source_context_snapshot_body_span_ck', 'c'),
            ('source_context_snapshot', 'source_context_snapshot_version_uq', 'u'),
            ('source_context_run', 'source_context_run_pkey', 'p'),
            ('source_context_run', 'source_context_run_source_ck', 'c'),
            ('source_context_run', 'source_context_run_mode_ck', 'c'),
            ('source_context_run', 'source_context_run_fingerprint_ck', 'c'),
            ('source_context_run', 'source_context_run_status_ck', 'c'),
            ('source_context_run', 'source_context_run_total_ck', 'c'),
            ('source_context_run', 'source_context_run_captured_ck', 'c'),
            ('source_context_run', 'source_context_run_excluded_ck', 'c'),
            ('source_context_run', 'source_context_run_failed_ck', 'c'),
            ('source_context_run', 'source_context_run_counts_ck', 'c'),
            ('source_context_outcome', 'source_context_outcome_pkey', 'p'),
            ('source_context_outcome', 'source_context_outcome_run_fkey', 'f'),
            ('source_context_outcome', 'source_context_outcome_source_ck', 'c'),
            ('source_context_outcome', 'source_context_outcome_payload_sha256_ck', 'c'),
            ('source_context_outcome', 'source_context_outcome_status_ck', 'c'),
            ('source_context_outcome', 'source_context_outcome_snapshot_fkey', 'f'),
            ('source_context_outcome', 'source_context_outcome_snapshot_ck', 'c'),
            ('source_context_outcome', 'source_context_outcome_run_record_uq', 'u')
        ) AS constraints(table_name, constraint_name, constraint_type)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = format('silver.%I', expected.table_name)::regclass
              AND conname = expected.constraint_name
              AND contype::text = expected.constraint_type
        ) THEN
            RAISE EXCEPTION 'incompatible constraint % on silver.%',
                expected.constraint_name, expected.table_name;
        END IF;
    END LOOP;
END $$;

-- Names and types are insufficient: a same-named UNIQUE/FK/CHECK can still
-- impose a different contract. Verify key columns, foreign-key targets/actions,
-- and exact canonical CHECK expressions compiled by PostgreSQL itself.
DO $$
DECLARE
    expected RECORD;
    actual_columns TEXT[];
    actual_target TEXT;
    actual_target_columns TEXT[];
    actual_delete_action TEXT;
    actual_definition TEXT;
    expected_definition TEXT;
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS _ctx_expected_snapshot_checks (
        source TEXT,
        payload_sha256 TEXT,
        header_start INTEGER,
        header_end INTEGER,
        body_start INTEGER,
        body_end INTEGER,
        CONSTRAINT source_context_snapshot_source_ck CHECK
            (source IN ('hn', 'eu_startups', 'yc')),
        CONSTRAINT source_context_snapshot_payload_sha256_ck CHECK
            (payload_sha256 ~ '^[0-9a-f]{64}$'),
        CONSTRAINT source_context_snapshot_header_span_ck CHECK (
            (header_start IS NULL AND header_end IS NULL)
            OR (header_start >= 0 AND header_end >= header_start)
        ),
        CONSTRAINT source_context_snapshot_body_span_ck CHECK (
            (body_start IS NULL AND body_end IS NULL)
            OR (body_start >= 0 AND body_end >= body_start)
        )
    );
    CREATE TEMP TABLE IF NOT EXISTS _ctx_expected_run_checks (
        source TEXT,
        mode TEXT,
        input_fingerprint TEXT,
        status TEXT,
        total_inputs INTEGER,
        captured_count INTEGER,
        excluded_count INTEGER,
        failed_count INTEGER,
        CONSTRAINT source_context_run_source_ck CHECK
            (source IN ('hn', 'eu_startups', 'yc')),
        CONSTRAINT source_context_run_mode_ck CHECK (mode IN ('capture')),
        CONSTRAINT source_context_run_fingerprint_ck CHECK
            (input_fingerprint ~ '^[0-9a-f]{64}$'),
        CONSTRAINT source_context_run_status_ck CHECK
            (status IN ('running', 'complete', 'partial', 'failed', 'interrupted')),
        CONSTRAINT source_context_run_total_ck CHECK (total_inputs >= 0),
        CONSTRAINT source_context_run_captured_ck CHECK (captured_count >= 0),
        CONSTRAINT source_context_run_excluded_ck CHECK (excluded_count >= 0),
        CONSTRAINT source_context_run_failed_ck CHECK (failed_count >= 0),
        CONSTRAINT source_context_run_counts_ck CHECK (
            captured_count + excluded_count + failed_count <= total_inputs
        )
    );
    CREATE TEMP TABLE IF NOT EXISTS _ctx_expected_outcome_checks (
        source TEXT,
        payload_sha256 TEXT,
        status TEXT,
        snapshot_id UUID,
        CONSTRAINT source_context_outcome_source_ck CHECK
            (source IN ('hn', 'eu_startups', 'yc')),
        CONSTRAINT source_context_outcome_payload_sha256_ck CHECK
            (payload_sha256 ~ '^[0-9a-f]{64}$'),
        CONSTRAINT source_context_outcome_status_ck CHECK
            (status IN ('captured', 'excluded', 'failed')),
        CONSTRAINT source_context_outcome_snapshot_ck CHECK (
            (status = 'captured' AND snapshot_id IS NOT NULL)
            OR (status <> 'captured' AND snapshot_id IS NULL)
        )
    );

    FOR expected IN
        SELECT * FROM (VALUES
            ('source_context_snapshot', 'source_context_snapshot_pkey', ARRAY['id']::text[]),
            ('source_context_snapshot', 'source_context_snapshot_version_uq', ARRAY['source','stable_id','payload_sha256','parser_version']::text[]),
            ('source_context_run', 'source_context_run_pkey', ARRAY['id']::text[]),
            ('source_context_outcome', 'source_context_outcome_pkey', ARRAY['id']::text[]),
            ('source_context_outcome', 'source_context_outcome_run_record_uq', ARRAY['run_id','source','stable_id']::text[])
        ) AS keys(table_name, constraint_name, columns)
    LOOP
        SELECT array_agg(a.attname ORDER BY k.ordinality) INTO actual_columns
        FROM pg_constraint c
        CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.conrelid = format('silver.%I', expected.table_name)::regclass
          AND c.conname = expected.constraint_name
          AND c.contype IN ('p', 'u');
        IF actual_columns IS DISTINCT FROM expected.columns THEN
            RAISE EXCEPTION 'incompatible key columns for silver.%.%',
                expected.table_name, expected.constraint_name;
        END IF;
    END LOOP;

    FOR expected IN
        SELECT * FROM (VALUES
            ('source_context_outcome', 'source_context_outcome_run_fkey', 'source_context_run', ARRAY['run_id']::text[], ARRAY['id']::text[], 'c'),
            ('source_context_outcome', 'source_context_outcome_snapshot_fkey', 'source_context_snapshot', ARRAY['snapshot_id']::text[], ARRAY['id']::text[], 'a')
        ) AS foreign_keys(table_name, constraint_name, target_table, columns, target_columns, delete_action)
    LOOP
        SELECT
            format('%I.%I', target_ns.nspname, target.relname),
            ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(attnum, ordinality)
                  JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum
                  ORDER BY k.ordinality),
            c.confdeltype::text,
            ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ordinality)
                  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                  ORDER BY k.ordinality)
        INTO actual_target, actual_target_columns, actual_delete_action, actual_columns
        FROM pg_constraint c
        JOIN pg_class target ON target.oid = c.confrelid
        JOIN pg_namespace target_ns ON target_ns.oid = target.relnamespace
        WHERE c.conrelid = format('silver.%I', expected.table_name)::regclass
          AND c.conname = expected.constraint_name
          AND c.contype = 'f';
        IF actual_target IS DISTINCT FROM format('silver.%I', expected.target_table)
           OR actual_target_columns IS DISTINCT FROM expected.target_columns
           OR actual_columns IS DISTINCT FROM expected.columns
           OR actual_delete_action IS DISTINCT FROM expected.delete_action THEN
            RAISE EXCEPTION 'incompatible foreign key silver.%.%',
                expected.table_name, expected.constraint_name;
        END IF;
    END LOOP;

    FOR expected IN
        SELECT * FROM (VALUES
            ('source_context_snapshot', '_ctx_expected_snapshot_checks', 'source_context_snapshot_source_ck'),
            ('source_context_snapshot', '_ctx_expected_snapshot_checks', 'source_context_snapshot_payload_sha256_ck'),
            ('source_context_snapshot', '_ctx_expected_snapshot_checks', 'source_context_snapshot_header_span_ck'),
            ('source_context_snapshot', '_ctx_expected_snapshot_checks', 'source_context_snapshot_body_span_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_source_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_mode_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_fingerprint_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_status_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_total_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_captured_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_excluded_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_failed_ck'),
            ('source_context_run', '_ctx_expected_run_checks', 'source_context_run_counts_ck'),
            ('source_context_outcome', '_ctx_expected_outcome_checks', 'source_context_outcome_source_ck'),
            ('source_context_outcome', '_ctx_expected_outcome_checks', 'source_context_outcome_payload_sha256_ck'),
            ('source_context_outcome', '_ctx_expected_outcome_checks', 'source_context_outcome_status_ck'),
            ('source_context_outcome', '_ctx_expected_outcome_checks', 'source_context_outcome_snapshot_ck')
        ) AS checks(table_name, expected_table, constraint_name)
    LOOP
        EXECUTE format(
            'SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c '
            'WHERE c.conrelid = %L::regclass AND c.conname = %L AND c.contype = ''c'' AND c.convalidated',
            'pg_temp.' || expected.expected_table, expected.constraint_name
        ) INTO expected_definition;
        SELECT pg_get_constraintdef(c.oid) INTO actual_definition
        FROM pg_constraint c
        WHERE c.conrelid = format('silver.%I', expected.table_name)::regclass
          AND c.conname = expected.constraint_name AND c.contype = 'c' AND c.convalidated;
        IF actual_definition IS NULL OR actual_definition IS DISTINCT FROM expected_definition THEN
            RAISE EXCEPTION 'incompatible check definition silver.%.%',
                expected.table_name, expected.constraint_name;
        END IF;
    END LOOP;
    DROP TABLE _ctx_expected_snapshot_checks;
    DROP TABLE _ctx_expected_run_checks;
    DROP TABLE _ctx_expected_outcome_checks;
END $$;
COMMIT;
