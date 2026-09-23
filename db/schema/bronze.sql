-- Bronze layer: raw ingestion, grouped by mechanism, not by source.
-- See architecture document section 4.1, ADR-0001, and
-- architecture-notes/elt-pipeline-and-scoring-decisions.md section 2.2.
--
-- All three tables share one shape by design: mechanism determines table
-- membership, not a column. `(source, stable_id)` is the uniqueness key;
-- a fetch whose content_hash matches the stored value for that key does
-- not insert a new row, it only bumps last_checked_at.

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE bronze.api_ingest (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id UUID NOT NULL,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, stable_id)
);

CREATE TABLE bronze.web_scrape_ingest (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id UUID NOT NULL,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, stable_id)
);

CREATE TABLE bronze.newsletter_ingest (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id UUID NOT NULL,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, stable_id)
);
