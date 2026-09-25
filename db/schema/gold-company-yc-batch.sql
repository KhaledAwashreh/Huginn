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
-- The guard is load-bearing, not defensive decoration. This file can add
-- yc_batch, removing it is the successor's job, and the successor is named so
-- that it sorts first ('notes' before 'yc-batch'). On a fresh install gold.sql
-- has already created notes, so the guard fires and this file does nothing;
-- unguarded, a brand-new database would end up carrying both columns.
--
-- Yielding when notes exists is necessary but not sufficient, and it is not
-- what makes the pair order-independent. This guard can only decline to
-- re-create a column the successor has already replaced, so the successor, not
-- this file, is what has to guarantee that notes exists by the time this file
-- runs. It does: gold-company-notes.sql creates notes unconditionally, ahead
-- of its own guard on yc_batch. It did not always, and for as long as it
-- returned early on a database carrying neither column, the pair lost in
-- filename order, this file running last and re-creating the column the
-- successor was meant to remove. The set exited 0 and the Gold writer then
-- failed on `column "notes" does not exist`. Reviewer SCHEMA-01,
-- docs/advisor/2026-09-25-code-review-findings.md.
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
