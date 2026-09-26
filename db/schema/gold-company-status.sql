-- Add gold.company.company_status: registry lifecycle status as the source
-- spells it (YC supplies 'Active', 'Inactive', 'Acquired', 'Public').
--
-- Nullable free text, not an enum or a CHECK, for the same reason
-- gold.company.stage is: constraining here would bake one registry's
-- vocabulary into the schema before a second registry exists.
--
-- Motivating gap: a Public company was indistinguishable from a seed-stage
-- startup, because gold.company had nowhere to record the difference. Oklo was
-- the example that surfaced it, though it is not the only one: 23 live
-- companies are now Public, not one.
--
-- A distinct axis from the two sibling columns, as they stood when this
-- migration was written (company_type has since been renamed legal_form, and
-- company_scale no longer uses the enterprise/startup/sme vocabulary, having
-- been replaced by headcount bands):
--   company_type    legal form ("Private Limited Company", "LLC")
--   company_scale   size bucket ('enterprise'/'startup'/'sme')
--   company_status  lifecycle ('Active'/'Public'/'Acquired'/'Inactive')
--
-- Type 1: not in TYPE_2_TRACKED_FIELDS, no gold.company_history
-- counterpart. Part of the open column classification in Jira KAN-20.
--
-- Idempotent.

ALTER TABLE gold.company
    ADD COLUMN IF NOT EXISTS company_status TEXT;
