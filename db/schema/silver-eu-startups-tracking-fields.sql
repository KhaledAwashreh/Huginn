-- Preserve EU-Startups tracking values in per-source Silver and carry the
-- two note-worthy values through cross-source resolution. Fresh databases
-- receive the same columns from silver.sql.

ALTER TABLE silver.eu_startups_listings
    ADD COLUMN IF NOT EXISTS founded TEXT;

ALTER TABLE silver.eu_startups_listings
    ADD COLUMN IF NOT EXISTS total_funding TEXT;

ALTER TABLE silver.eu_startups_listings
    ADD COLUMN IF NOT EXISTS company_status TEXT;

ALTER TABLE silver.resolved_signals
    ADD COLUMN IF NOT EXISTS founded TEXT;

ALTER TABLE silver.resolved_signals
    ADD COLUMN IF NOT EXISTS total_funding TEXT;
