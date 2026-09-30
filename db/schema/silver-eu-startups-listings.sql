-- Add the EU-Startups per-source staging table to an existing database.
-- Fresh databases receive the same definition from silver.sql.

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.eu_startups_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stable_id TEXT NOT NULL,
    company_name_raw TEXT NOT NULL,
    website TEXT,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('hiring', 'funding', 'program_milestone', 'other')),
    stage TEXT,
    description TEXT,
    occurred_on TIMESTAMPTZ,
    url TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (stable_id)
);
