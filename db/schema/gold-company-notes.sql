-- gold.company.yc_batch becomes gold.company.notes: a single free-text column
-- for source-attributed notes, not one column per source per fact.
--
-- Why the shape changed. yc_batch held YC's funded-batch label verbatim, which
-- made the column's name a claim that only YC would ever fill it. A second
-- portal's batch, founding year, or registry field is inevitable, and adding a
-- column per source per fact does not scale. So the column becomes `notes` and
-- every value carries a source prefix: 'YC Summer 2023'. A reader can
-- still tell whose statement it is; the schema just stops asserting that YC is
-- the only source with something to say.
--
-- The batch itself is NOT company age and NOT occurred_at, which carries YC's
-- unrelated launched_at. Verified live: the 90-company 'Fall 2026' batch has 90
-- distinct launched_at values spanning 19 months, and every batch from Summer
-- 2005 to Winter 2011 has its earliest launched_at on exactly 2012-01-17, a
-- profile backfill wave.
--
-- Data is preserved rather than dropped. Existing yc_batch values are rewritten
-- into the prefixed form before the old column goes, so a database upgraded
-- without a Gold re-run still reads correctly. A YC-sourced NULL stays NULL:
-- 'no note' and 'an empty note' are different claims, and an empty string
-- would read as the latter. The rewrite is guarded so that re-running against
-- an already-migrated table, where yc_batch no longer exists, is a no-op
-- rather than an error.
--
-- Type 1, no company_history counterpart: a note is descriptive, so a change
-- in wording is not a recorded attribute change.
--
-- This file, not gold-company-yc-batch.sql, is the authority on the shape of
-- gold.company, and it converges on `notes` in either apply order. The
-- invariant: once it has run, gold.company.notes exists and gold.company.yc_batch
-- does not.
--
-- That holds because `notes` is created unconditionally, ahead of the guard on
-- yc_batch. Guarding the create instead, which is what an earlier version of
-- this file did, breaks the pair: the superseded file only declines to re-add
-- yc_batch when notes already exists, so on a database carrying neither column
-- the successor skipped its own work and the superseded file ran last in
-- filename order and won. The set exited 0 having left a table with only
-- yc_batch, so the first Gold write of a company failed on `column "notes"
-- does not exist`, and a second pass silently repaired it, which is worse than
-- a clean break because the README documents a single pass. Reviewer SCHEMA-01,
-- docs/advisor/2026-09-25-code-review-findings.md.
--
-- Idempotent.

DO $$
DECLARE
    has_yc_batch BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = 'company'
          AND column_name = 'yc_batch'
    ) INTO has_yc_batch;

    -- Unconditional, and ahead of the guard below. The guard covers the
    -- rewrite, not the shape of the table: on a database with neither column
    -- this is the only statement that creates notes, so an early return ahead
    -- of it hands the outcome to whichever of the pair runs last.
    ALTER TABLE gold.company
        ADD COLUMN IF NOT EXISTS notes TEXT;

    IF NOT has_yc_batch THEN
        RETURN;
    END IF;

    -- Prefix before dropping, so the values survive the rename. Matches
    -- what CompanyWriter now writes for a YC-sourced batch. The notes guard
    -- keeps a second pass from prefixing a prefix.
    UPDATE gold.company
    SET notes = 'YC ' || yc_batch
    WHERE yc_batch IS NOT NULL
      AND (notes IS NULL OR notes = '');

    ALTER TABLE gold.company
        DROP COLUMN yc_batch;
END
$$;
