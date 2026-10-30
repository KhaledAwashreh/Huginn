-- Explicit first-install source boundary, not evidence of a completed crawl.
-- Apply after kan-83-eu-startups-discovery.sql. Only absent state is seeded.
-- Listings last-modified before this 365-day boundary are intentionally excluded
-- from initial discovery; durable retry records are preserved and replay separately.
BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '10s';
-- Same lock as PostgresEuStartupsDiscoveryRepository.commit_batch.
SELECT pg_advisory_xact_lock(1213548361, 1163219796);
INSERT INTO bronze.eu_startups_discovery_state (singleton, watermark)
VALUES (TRUE, CURRENT_TIMESTAMP - INTERVAL '365 days')
ON CONFLICT (singleton) DO NOTHING;
COMMIT;
