-- silver.yc_listings and silver.resolved_signals gain former_names, the
-- company's prior names as YC spells them.
--
-- Stored, not used. former_names can only produce entity-resolution recall
-- once something matches a name against a set of known names, and nothing
-- does: src/huginn/elt/silver/resolution.py derives every key one-sidedly
-- from a domain (4,431 domain_normalized and 193 unresolved in
-- silver.resolved_signals today), and its fuzzy_match() is still
-- NotImplementedError pending Jira KAN-4. Reading this column to
-- resolve a company would mean building that matcher here, which is KAN-4
-- and not a schema change.
--
-- Captured now anyway, for the same reason industries is: 3,054 of the
-- 6,252 live YC rows in bronze.api_ingest carry at least one former
-- name, and Silver is the layer whose job is faithful capture. Deferring
-- it would leave a known-present source field unavailable and cost a
-- second full backfill from bronze later. On silver.yc_listings the
-- column is non-null on all 4,349 live rows, 2,064 of them an empty
-- array rather than a list of names, and that stays distinct from NULL,
-- which is the key being absent. Note the values are not necessarily
-- clean names, e.g.
--
--   ['InnerSpace', 'InnerSpace / Leaders In Tech', 'Leaders In Tech (formerly InnerSpace)']
--
-- so whoever builds the matcher decides how to treat a self-referential
-- entry; keeping the raw list means that decision can be made against the
-- data rather than baked into a pre-cleaned column.
--
-- Text array rather than a separate names table: one company has a handful
-- of former names, they are read only with their company, and nothing
-- queries across names yet.
--
-- Idempotent.

ALTER TABLE silver.yc_listings
    ADD COLUMN IF NOT EXISTS former_names TEXT[];

ALTER TABLE silver.resolved_signals
    ADD COLUMN IF NOT EXISTS former_names TEXT[];
