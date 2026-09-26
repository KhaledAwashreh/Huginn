-- KAN-41 / ADR-0007: gold.company_signal gains source_stable_id plus the
-- (source, source_stable_id) uniqueness that makes a re-run upsert the
-- same fact row instead of duplicating it.
--
-- Why this file exists: the KAN-41 commit d0f37ab changed only
-- db/schema/gold.sql, which is the fresh-install path. It shipped no ALTER
-- for a database that already existed, so any existing deployment keeps a
-- gold.company_signal with no source_stable_id column and no natural-key
-- constraint, and the KAN-41 repository's INSERT fails with
-- psycopg.errors.UndefinedColumn. This is the same gap that
-- gold-company-stage.sql, gold-company-scale.sql, and
-- gold-company-status.sql close for gold.company.
--
-- Row-count precondition: the pre-KAN-41 schema has no source_stable_id
-- column at all, so there is no correct value to backfill onto an existing
-- row. Inventing a placeholder would permanently poison the natural key
-- that ADR-0007 exists to make trustworthy. gold.company_signal is a
-- derived fact table, fully rebuildable from silver.resolved_signals, so
-- this migration refuses and tells the operator to truncate and re-run
-- rather than guessing:
--
--   TRUNCATE gold.company_signal;
--
-- The precondition tests for the absence of the column, not for a
-- non-empty table. The two are not the same condition, and conflating them
-- breaks the common case: once this file has run once, the table has rows
-- *and* a column, and re-running the file is what an operator does after
-- collecting facts. Keying on emptiness would make this non-idempotent for
-- precisely the database it exists to fix. So there are three states:
--
--   column present                    -> already migrated, no-op, rows are fine
--   column absent, table empty        -> safe to add the column
--   column absent, table has rows     -> cannot backfill, refuse (below)
--
-- Idempotent.

DO $$
DECLARE
    has_source_stable_id BOOLEAN;
    has_rows BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = 'company_signal'
          AND column_name = 'source_stable_id'
    ) INTO has_source_stable_id;

    IF has_source_stable_id THEN
        RETURN;
    END IF;

    SELECT EXISTS (SELECT 1 FROM gold.company_signal) INTO has_rows;

    IF has_rows THEN
        RAISE EXCEPTION
            'gold.company_signal has rows but no source_stable_id column, so its '
            'existing rows predate ADR-0007''s natural key and no correct value '
            'can be backfilled. It is a derived fact table: TRUNCATE '
            'gold.company_signal and re-run the Gold signal writer to repopulate '
            'it from silver.resolved_signals.';
    END IF;
END
$$;

ALTER TABLE gold.company_signal
    ADD COLUMN IF NOT EXISTS source_stable_id TEXT;

ALTER TABLE gold.company_signal
    ALTER COLUMN source_stable_id SET NOT NULL;

-- Constraint name matches what a fresh install of db/schema/gold.sql
-- produces, so the two paths converge on one schema.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'gold.company_signal'::regclass
          AND conname = 'company_signal_source_source_stable_id_key'
    ) THEN
        ALTER TABLE gold.company_signal
            ADD CONSTRAINT company_signal_source_source_stable_id_key
            UNIQUE (source, source_stable_id);
    END IF;
END
$$;
