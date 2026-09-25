-- SUPERSEDED by gold-company-notes.sql. Kept so a database that already ran
-- this file is not left with a half-applied pair, and guarded so it cannot
-- undo the successor.
--
-- What this originally did: added gold.company.yc_batch, holding the funded
-- batch a company joined YC in, carried through from silver verbatim
-- (db/schema/silver-yc-batch.sql). Type 1, no company_history counterpart.
--
-- Why it was superseded: a column named for one source asserts that only that
-- source will ever fill it. A second portal's batch, founding year, or registry
-- field is inevitable, and a column per source per fact does not scale, so
-- gold.company.notes replaces it, each value opening with its source
-- ('YC Summer 2023').
--
-- The guard is load-bearing, not defensive decoration. Migrations are applied
-- in filename order and the successor sorts FIRST ('notes' before 'yc-batch'),
-- so on a fresh install the sequence is: gold.sql creates notes,
-- gold-company-notes.sql finds no yc_batch and correctly does nothing, and
-- then this file would run last and re-add the very column the successor
-- removed. Unguarded, a brand-new database ends up with both notes and
-- yc_batch. Yielding when notes exists makes the pair order-independent.
--
-- Idempotent.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = 'company'
          AND column_name = 'notes'
    ) THEN
        RETURN;
    END IF;

    ALTER TABLE gold.company
        ADD COLUMN IF NOT EXISTS yc_batch TEXT;
END
$$;
