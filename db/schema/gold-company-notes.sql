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

    IF NOT has_yc_batch THEN
        RETURN;
    END IF;

    ALTER TABLE gold.company
        ADD COLUMN IF NOT EXISTS notes TEXT;

    -- Prefix before dropping, so the values survive the rename. Matches
    -- what CompanyWriter now writes for a YC-sourced batch.
    UPDATE gold.company
    SET notes = 'YC ' || yc_batch
    WHERE yc_batch IS NOT NULL
      AND (notes IS NULL OR notes = '');

    ALTER TABLE gold.company
        DROP COLUMN yc_batch;
END
$$;
