-- gold.company.business_sector widens from TEXT to TEXT[]: a company sits in
-- more than one sector, and YC says so (4,899 of the 6,252 live
-- bronze.api_ingest YC payloads report more than one industry).
-- gold.company_history.business_sector follows so a history row records the
-- same shape as the current row it describes.
--
-- The USING clause is not optional and is not a plain cast, both verified
-- against Postgres 16:
--
--   TYPE TEXT[]              -> error, no assignment cast exists
--   USING business_sector::text[]
--                             -> error, 'malformed array literal', because
--                                the cast routes a text value through array
--                                input parsing rather than wrapping it
--   USING CASE ... array[c]  -> correct
--
-- So a database that still had a scalar populated degrades it to a
-- one-element array rather than failing the migration. The NULL branch
-- preserves a NULL as NULL rather than as '{}', because an empty array
-- would read as "known to have no sectors" when the truth is "not
-- classified yet". The branch is still load-bearing: 4,337 of the
-- 4,423 live gold.company rows are populated and every one of them is
-- single-dimensional, but 86 are NULL and must stay NULL.
--
-- Idempotent, and the type guard is the load-bearing part. Without it,
-- re-running against an already-migrated column re-applies
-- ARRAY[business_sector] to a TEXT[] and wraps every value one dimension
-- deeper: 'Fintech' becomes '{{Fintech}}' and '{"B2B","Fintech"}' becomes
-- '{{B2B,Fintech}}'. Postgres raises no error for that, the column type
-- stays text[], and cardinality() still returns 2, so the damage is silent
-- until something asserts a dimension or the Type 2 history path compares a
-- re-read value against the single-dimension list it just wrote.
-- Verified against Postgres 16, on a populated column of that shape, so
-- the guard tests the column's current type rather than assuming a
-- re-run is inert.
--
-- A pg_typeof test inside the USING expression does not work: while the
-- column is still TEXT, Postgres resolves the CASE's branches at plan time
-- and fails with 'CASE types text and text[] cannot be matched' before the
-- guard could ever be evaluated. Hence the DO block.

DO $$
DECLARE
    is_still_scalar BOOLEAN;
BEGIN
    SELECT data_type = 'text' INTO is_still_scalar
    FROM information_schema.columns
    WHERE table_schema = 'gold'
      AND table_name = 'company'
      AND column_name = 'business_sector';

    IF is_still_scalar THEN
        ALTER TABLE gold.company
            ALTER COLUMN business_sector TYPE TEXT[]
            USING CASE
                WHEN business_sector IS NULL THEN NULL
                ELSE ARRAY[business_sector]::TEXT[]
            END;

        ALTER TABLE gold.company_history
            ALTER COLUMN business_sector TYPE TEXT[]
            USING CASE
                WHEN business_sector IS NULL THEN NULL
                ELSE ARRAY[business_sector]::TEXT[]
            END;
    END IF;
END
$$;

-- business_sector IS NULL is the parked OpenCorporates enrichment worklist
-- (read_unenriched_company_names). Once YC populates this column, that query
-- returns only companies YC did not classify, which is a different set from
-- 'not yet looked up'. Whoever resumes that path needs a separate marker
-- column, because a company's data and whether it has been looked up yet are
-- not the same thing. Left as-is deliberately: that source cannot run, so
-- there is nothing to keep working.
