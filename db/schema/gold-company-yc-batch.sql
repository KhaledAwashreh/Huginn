-- gold.company gains yc_batch: the funded batch a company joined YC in,
-- carried through from silver verbatim (db/schema/silver-yc-batch.sql).
--
-- Typed 1, not history-tracked. A company joins YC once and stays in that
-- batch for the rest of its life, so the value cannot change and there is
-- nothing for a gold.company_history row to record. No matching column on
-- company_history, unlike business_sector, which is genuinely re-classified
-- over time. See ADR-0002 and gold/dimensional.py TYPE_2_TRACKED_FIELDS.
--
-- Prefixed rather than named plain `batch`, because "batch" alone does not
-- say which portal assigned it, and the other source-specific Gold columns
-- follow the same convention of naming the source where two sources could
-- disagree (company_status names the registry, company_scale is Huginn's own
-- vocabulary). A second portal with its own batches would need its own
-- column rather than overwriting this one.
--
-- No check constraint. The values are YC's own strings and the vocabulary is
-- not Huginn's to constrain, the same reasoning that leaves gold.stage and
-- gold.company_status unconstrained.
--
-- Idempotent.

ALTER TABLE gold.company
    ADD COLUMN IF NOT EXISTS yc_batch TEXT;
