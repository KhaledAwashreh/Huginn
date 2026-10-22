-- Canonical additive lifecycle schema. Apply after the base schemas.
-- See docs/source-currentness.md. Does not reconcile or alter existing evidence.
BEGIN;
SET LOCAL search_path = pg_catalog, public;

-- These temporary definitions are also the compatibility contract on rerun.
-- LIKE copies columns, checks, defaults and unique indexes; foreign keys are
-- installed separately because PostgreSQL deliberately does not copy them.
CREATE TEMP TABLE _lifecycle_expected_observation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL CHECK (source IN ('hn', 'yc', 'eu_startups')),
    stable_id TEXT NOT NULL CHECK (length(stable_id) > 0),
    raw_token TEXT NOT NULL CHECK (raw_token ~ '^[0-9a-f]{32}$'),
    resolution_token TEXT NOT NULL CHECK (resolution_token ~ '^[0-9a-f]{32}$'),
    policy_version TEXT NOT NULL CHECK (length(policy_version) > 0),
    context_version TEXT NOT NULL CHECK (length(context_version) > 0),
    snapshot_id UUID,
    listing_state TEXT NOT NULL CHECK
        (listing_state IN ('available', 'withdrawn', 'invalid', 'unknown')),
    hiring_state TEXT NOT NULL CHECK
        (hiring_state IN ('true', 'false', 'unknown', 'not_applicable')),
    identity_state TEXT NOT NULL CHECK
        (identity_state IN ('consistent', 'unresolved', 'mismatch', 'missing')),
    reason TEXT NOT NULL CHECK (length(reason) > 0),
    explicit_domain TEXT,
    resolved_company_key TEXT,
    key_derivation TEXT,
    company_id UUID,
    occurred_at TIMESTAMPTZ,
    bronze_fetched_at TIMESTAMPTZ NOT NULL,
    bronze_last_checked_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, stable_id, id)
) ON COMMIT DROP;

DO $$
BEGIN
    IF to_regclass('silver.source_lifecycle_observation') IS NULL THEN
        CREATE TABLE silver.source_lifecycle_observation
            (LIKE _lifecycle_expected_observation INCLUDING ALL);
        ALTER TABLE silver.source_lifecycle_observation
            ADD FOREIGN KEY (snapshot_id) REFERENCES silver.source_context_snapshot(id),
            ADD FOREIGN KEY (company_id) REFERENCES gold.company(id);
    END IF;
END $$;

CREATE TEMP TABLE _lifecycle_expected_current (
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    current_observation_id UUID NOT NULL,
    last_reconciled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, stable_id)
) ON COMMIT DROP;

DO $$
BEGIN
    IF to_regclass('silver.source_currentness') IS NULL THEN
        CREATE TABLE silver.source_currentness
            (LIKE _lifecycle_expected_current INCLUDING ALL);
        ALTER TABLE silver.source_currentness
            ADD FOREIGN KEY (source, stable_id, current_observation_id)
                REFERENCES silver.source_lifecycle_observation (source, stable_id, id);
    END IF;
END $$;

DO $$
DECLARE
    pair RECORD;
    expected_columns JSONB;
    actual_columns JSONB;
    expected_constraints TEXT[];
    actual_constraints TEXT[];
BEGIN
    FOR pair IN SELECT * FROM (VALUES
        ('silver.source_lifecycle_observation', 'pg_temp._lifecycle_expected_observation'),
        ('silver.source_currentness', 'pg_temp._lifecycle_expected_current')
    ) AS pairs(actual, expected)
    LOOP
        -- Include exact column order, type, nullability and defaults. A same-name
        -- table must not silently accept a weaker or unrelated definition.
        SELECT jsonb_agg(jsonb_build_array(a.attname, a.atttypid, a.atttypmod,
                    a.attnotnull, pg_get_expr(d.adbin, d.adrelid)) ORDER BY a.attnum)
        INTO expected_columns
        FROM pg_attribute a LEFT JOIN pg_attrdef d
            ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE a.attrelid = pair.expected::regclass AND a.attnum > 0 AND NOT a.attisdropped;
        SELECT jsonb_agg(jsonb_build_array(a.attname, a.atttypid, a.atttypmod,
                    a.attnotnull, pg_get_expr(d.adbin, d.adrelid)) ORDER BY a.attnum)
        INTO actual_columns
        FROM pg_attribute a LEFT JOIN pg_attrdef d
            ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE a.attrelid = pair.actual::regclass AND a.attnum > 0 AND NOT a.attisdropped;
        SELECT array_agg(contype::text || ':' || pg_get_constraintdef(oid)
                         ORDER BY contype::text || ':' || pg_get_constraintdef(oid))
        INTO expected_constraints FROM pg_constraint
        WHERE conrelid = pair.expected::regclass;
        SELECT array_agg(contype::text || ':' || pg_get_constraintdef(oid)
                         ORDER BY contype::text || ':' || pg_get_constraintdef(oid))
        INTO actual_constraints FROM pg_constraint
        WHERE conrelid = pair.actual::regclass AND contype <> 'f';
        IF actual_columns IS DISTINCT FROM expected_columns
           OR actual_constraints IS DISTINCT FROM expected_constraints THEN
            RAISE EXCEPTION 'incompatible lifecycle schema: %', pair.actual;
        END IF;
    END LOOP;
    SELECT array_agg(definition ORDER BY definition) INTO expected_constraints
    FROM (VALUES
        ('silver.source_lifecycle_observation:FOREIGN KEY (snapshot_id) REFERENCES silver.source_context_snapshot(id)'),
        ('silver.source_lifecycle_observation:FOREIGN KEY (company_id) REFERENCES gold.company(id)'),
        ('silver.source_currentness:FOREIGN KEY (source, stable_id, current_observation_id) REFERENCES silver.source_lifecycle_observation(source, stable_id, id)')
    ) AS expected(definition);
    SELECT array_agg(conrelid::regclass::text || ':' || pg_get_constraintdef(oid)
                    ORDER BY conrelid::regclass::text || ':' || pg_get_constraintdef(oid))
    INTO actual_constraints FROM pg_constraint
    WHERE conrelid IN ('silver.source_lifecycle_observation'::regclass,
                      'silver.source_currentness'::regclass) AND contype = 'f';
    IF actual_constraints IS DISTINCT FROM expected_constraints THEN
        RAISE EXCEPTION 'incompatible lifecycle schema foreign keys';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS source_lifecycle_snapshot_idx
    ON silver.source_lifecycle_observation (snapshot_id);
CREATE INDEX IF NOT EXISTS source_lifecycle_company_idx
    ON silver.source_lifecycle_observation (company_id);
CREATE INDEX IF NOT EXISTS source_currentness_observation_idx
    ON silver.source_currentness (current_observation_id);

CREATE OR REPLACE FUNCTION silver.reject_lifecycle_history_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'source lifecycle observations are immutable'
        USING ERRCODE = '55000';
END $$;
DROP TRIGGER IF EXISTS source_lifecycle_immutable
    ON silver.source_lifecycle_observation;
CREATE TRIGGER source_lifecycle_immutable
    BEFORE UPDATE OR DELETE ON silver.source_lifecycle_observation
    FOR EACH ROW EXECUTE FUNCTION silver.reject_lifecycle_history_mutation();

COMMIT;
