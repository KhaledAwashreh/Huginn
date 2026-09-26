-- gold.company.company_type becomes gold.company.legal_form.
--
-- Why: the column holds a legal form ("Private Limited Company", "LLC",
-- "C Corp"), and `company_type` said nothing about that. It also sat in a
-- family of `company_`-prefixed columns holding three unrelated axes, which is
-- what made it read as a second size classification alongside
-- `company_scale`. That misreading is not hypothetical: the same confusion is
-- why the column was a size CHECK constraint once, split off into
-- `company_scale` by gold-company-scale.sql, and left holding legal forms
-- under the old name.
--
-- `legal_form` is the term this repo's own prose already used. db/schema/gold.sql
-- opened its comment with "Legal form, free text", docs/entities.md said "legal
-- form, free text and jurisdiction specific", and
-- architecture-notes/opencorporates-fetch-plan.md section 4 said
-- "OpenCorporates' company_type is a legal form". The rename makes the code
-- agree with documentation that was already correct.
--
-- Rejected alternatives:
--
--   legal_classification: "classification" already means business_sector and
--     the company_scale bands in this schema, and it implies a controlled
--     vocabulary. This column is deliberately the opposite, unconstrained free
--     text with unbounded jurisdiction-specific values, and a name implying an
--     enum invites re-adding the CHECK that caused the original problem.
--   legal_type: ambiguous about type of what, and readable as legal status,
--     which is company_status, a different column on a different axis.
--   incorporation_type: would wrongly exclude forms that are not
--     incorporations, such as partnerships, trusts and sole proprietorships.
--
-- No data migration: the column is NULL on all 4,423 live rows and no writer
-- anywhere in the tree sets it. Its intended source, OpenCorporates' legal
-- form, is parked, so nothing references the old name but this file and the
-- allowlist in gold/repositories/company_repository.py.
--
-- Renamed rather than dropped and re-added so the column's history in the
-- database is continuous, and so an existing database that already has the
-- column keeps it instead of silently losing the definition.
--
-- Idempotent. Renaming a column that does not exist is a no-op only when
-- guarded, so the DO block checks first; without it, re-running against an
-- already-renamed database would raise.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = 'company'
          AND column_name = 'company_type'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = 'company'
          AND column_name = 'legal_form'
    ) THEN
        ALTER TABLE gold.company
            RENAME COLUMN company_type TO legal_form;
    END IF;
END
$$;
