-- Add gold.company.stage.
--
-- gold.company_signal already has a `stage` column (the fact grain: the
-- stage as of that signal). This adds the dimension-grain equivalent, the
-- company's current stage. architecture document section 7 lists stage as
-- a v1 scoring input; it had no column on the dimension to land in.
--
-- Populated from silver.yc_listings.stage, which holds YC's 'Early' /
-- 'Growth' on all 6252 YC rows. HN supplies no stage, so HN-only
-- companies stay NULL.
--
-- Type 1, not Type 2: not added to TYPE_2_TRACKED_FIELDS in
-- huginn.elt.gold.dimensional, and no matching column on
-- gold.company_history. A stage transition (Early -> Growth) is arguably
-- a Type 2 event, but that classification is part of the open
-- column-by-column work in Jira KAN-20, and making it Type 2 also needs
-- a company_history column and a change to insert_history's SQL. Kept
-- out of scope here deliberately.
--
-- Idempotent.

ALTER TABLE gold.company
    ADD COLUMN IF NOT EXISTS stage TEXT;
