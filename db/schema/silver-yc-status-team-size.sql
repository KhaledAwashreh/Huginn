-- Carry YC's registry status and headcount from bronze through Silver so
-- Gold has something to derive gold.company.company_status and
-- gold.company.company_scale from.
--
-- Two columns, added at two layers:
--   silver.yc_listings      company_status, team_size
--   silver.resolved_signals company_status, team_size
--
-- Why silver.resolved_signals needs them at all: Gold's dimension is
-- built from resolved_signals (architecture document section 4.3), not
-- from the per-source staging tables, so anything Gold populates has to
-- survive the resolution step.
--
-- Why they are YC-only on the staging table: HN's "Who's Hiring" comments
-- carry no registry status and no headcount. ADR-0001 anticipated this
-- case, letting a source-specific staging column exist on just one
-- source's table rather than as a meaningless nullable column on all of
-- them. On the cross-source resolved_signals table they are nullable
-- regardless, NULL for every HN row.
--
-- team_size is stored as a raw integer, not a band. The four headcount
-- bands are Huginn's vocabulary, not YC's, so the bucketing belongs in
-- Gold (section 4.3), not in the layer that faithfully conforms a source.
--
-- Idempotent.

ALTER TABLE silver.yc_listings
    ADD COLUMN IF NOT EXISTS company_status TEXT;

ALTER TABLE silver.yc_listings
    ADD COLUMN IF NOT EXISTS team_size INTEGER;

ALTER TABLE silver.resolved_signals
    ADD COLUMN IF NOT EXISTS company_status TEXT;

ALTER TABLE silver.resolved_signals
    ADD COLUMN IF NOT EXISTS team_size INTEGER;
