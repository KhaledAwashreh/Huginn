-- One-off additive KAN-83 upgrade for pre-existing Bronze schemas.
-- This is also applied during fresh bootstrap; it is not migration tooling.

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.eu_startups_discovery_state (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    watermark TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bronze.eu_startups_listing_retry (
    url TEXT PRIMARY KEY,
    lastmod TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL CHECK (attempt_count > 0),
    terminal_attempt_count INTEGER NOT NULL
        CHECK (terminal_attempt_count >= 0),
    last_status_code INTEGER,
    status TEXT NOT NULL CHECK (status IN ('retryable', 'terminal')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS eu_startups_listing_retry_retryable_order_idx
    ON bronze.eu_startups_listing_retry (lastmod, url)
    WHERE status = 'retryable';

CREATE INDEX IF NOT EXISTS web_scrape_ingest_eu_startups_url_idx
    ON bronze.web_scrape_ingest ((payload ->> 'url'))
    WHERE source = 'eu_startups';
