-- Add gold.company.company_status: registry lifecycle status as the source
-- spells it (YC supplies 'Active', 'Inactive', 'Acquired', 'Public').
--
-- Nullable free text, not an enum or a CHECK, for the same reason
-- gold.company.stage is: constraining here would bake one registry's
-- vocabulary into the schema before a second registry exists.
--
-- Motivating gap: Oklo is 'Public' while every other company in the dev
-- database is 'Active', and gold.company had nowhere to record the
-- difference, so a public company and a seed-stage startup were
-- indistinguishable.
--
-- A distinct axis from the two sibling columns:
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
