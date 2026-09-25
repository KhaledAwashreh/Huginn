-- silver.yc_listings and silver.resolved_signals gain batch: the funded
-- batch a company joined YC in, as YC spells it ('Winter 2022').
--
-- This is the date Huginn actually wants for "when did this company join the
-- portal", and it is NOT the date already stored in occurred_on. occurred_on
-- carries YC's `launched_at`, which is a separate and largely independent
-- event. Verified live on all 6,252 YC rows:
--
--   * The 90-company 'Fall 2026' batch has 90 distinct launched_at values
--     spanning 19 months, so launched_at is not a per-batch constant.
--   * Every batch from Summer 2005 to Winter 2011 has its earliest
--     launched_at on exactly 2012-01-17: a profile backfill wave, years
--     after those companies were funded.
--   * Winter 2026's earliest launched_at is 2023-08-02, three years before
--     the batch.
--
-- The documented third example is Airbnb: founded August 2008, batch W09,
-- launched_at 2012-01-17. Three different dates, so neither launched_at nor
-- any date derived from it stands in for the batch.
--
-- Kept as the source's label string rather than split into a season and a
-- year, because the label is what the source publishes and what a human
-- reading a digest recognizes. It is a low-cardinality closed-ish set:
-- 51 distinct values on live data, spanning 'Summer 2005' to 'Winter 2027',
-- plus exactly one row reading 'Unspecified'. That literal is stored as
-- given rather than folded into NULL: it is the source stating it has no
-- batch, which is a different claim from the key being absent.
--
-- Founded date is deliberately absent and cannot be added from this source.
-- YC's Algolia payload, which is what Bronze lands, carries no founding
-- date at all. The YC profile page does publish `year_founded`, but reaching
-- it means scraping ycombinator.com/companies/<slug>, a different ingestion
-- mechanism, not a column on these tables.
--
-- Idempotent.

ALTER TABLE silver.yc_listings
    ADD COLUMN IF NOT EXISTS batch TEXT;

ALTER TABLE silver.resolved_signals
    ADD COLUMN IF NOT EXISTS batch TEXT;
