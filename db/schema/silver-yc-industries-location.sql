-- YC supplies two more fields this schema did not carry: `industries`
-- (a list, so TEXT[] rather than TEXT) and `all_locations` (a freeform
-- display string, kept verbatim so Gold owns the parse into country/city).
--
-- Same gap the other YC ALTER files close: a schema change made only in
-- db/schema/silver.sql exists for fresh installs alone.
--
-- industries is nullable rather than NOT NULL DEFAULT '{}' on purpose. An
-- empty array and a NULL mean different things here: NULL is 'this source
-- does not report industries', which is what every HN row has and what Gold
-- must not read as a value that clears a YC-supplied one. '{}' would
-- conflate the two and make a missing list indistinguishable from an
-- explicitly empty one.
--
-- Idempotent.

ALTER TABLE silver.yc_listings
    ADD COLUMN IF NOT EXISTS industries TEXT[],
    ADD COLUMN IF NOT EXISTS all_locations TEXT;

ALTER TABLE silver.resolved_signals
    ADD COLUMN IF NOT EXISTS industries TEXT[],
    ADD COLUMN IF NOT EXISTS all_locations TEXT;
