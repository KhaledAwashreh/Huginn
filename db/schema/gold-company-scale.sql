-- Split gold.company's overloaded company_type into two columns on two
-- different axes.
--
-- Before: company_type TEXT CHECK (company_type IN ('enterprise',
-- 'startup', 'sme')). Those three values are a size/structure
-- classification, but the column name says legal form, and
-- architecture-notes/opencorporates-fetch-plan.md section 4 documents the
-- resulting hazard: OpenCorporates' company_type is a legal form
-- ("Private Limited Company", "LLC"), so mapping it here would silently
-- corrupt the column.
--
-- After:
--   company_scale  the size/structure bucket, keeps the CHECK, but as the
--                  four headcount bands ('0-10', '11-100', '101-1000',
--                  '1001+') rather than 'enterprise'/'startup'/'sme'.
--                  A directory or registry of startups would classify
--                  100% of its rows as 'startup', so that vocabulary
--                  discriminates nothing and collides with the separate
--                  stage column. Headcount bands are objective.
--   company_type    free text, legal form, unconstrained because legal
--                  forms are jurisdiction specific and unbounded.
--
-- No data migration needed: company_type is NULL on every row, and no
-- code reads or writes it. Only the CHECK moves.
--
-- company_scale is not in TYPE_2_TRACKED_FIELDS and has no
-- gold.company_history counterpart, so it is Type 1. That classification
-- is still open in Jira KAN-20.
--
-- Idempotent.

ALTER TABLE gold.company
    ADD COLUMN IF NOT EXISTS company_scale TEXT;

-- Drop-then-add, because Postgres has no ADD CONSTRAINT IF NOT EXISTS and
-- this file must be safely re-runnable.
--
-- Both names are dropped because a database can arrive here from either
-- direction. A fresh install that also ran this file already has
-- company_scale_check, which db/schema/gold.sql now names explicitly for
-- exactly this reason. A database created before that naming did, and still
-- carries the auto-generated company_company_scale_check. Dropping only one
-- would leave a fresh install with a duplicate pair that the next band-list
-- change updates in one place and not the other, so a value the new list
-- allows would be rejected by the stale constraint. Reviewer SCHEMA-02.
ALTER TABLE gold.company
    DROP CONSTRAINT IF EXISTS company_company_scale_check;

ALTER TABLE gold.company
    DROP CONSTRAINT IF EXISTS company_scale_check;

ALTER TABLE gold.company
    ADD CONSTRAINT company_scale_check
    CHECK (company_scale IN ('0-10', '11-100', '101-1000', '1001+'));

-- Move the size CHECK off company_type, leaving it free text. The
-- auto-generated name from the original inline CHECK is
-- company_company_type_check (table-name prefix, not schema-qualified).
-- The column has since been renamed to legal_form; the constraint was
-- already gone by then, so there is nothing to rename here.
ALTER TABLE gold.company
    DROP CONSTRAINT IF EXISTS company_company_type_check;
