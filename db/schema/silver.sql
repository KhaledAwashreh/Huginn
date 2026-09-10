-- Silver layer: per-source staging, cross-source entity resolution.
-- See architecture document section 4.2, ADR-0001, and docs/entities.md.
--
-- Staging tables share one shape by design (ADR-0001): kept separate per
-- source so operational mistakes and transform bugs stay scoped to one
-- source. resolved_signals stays at event grain (one row per signal),
-- deliberately not split into company/signal tables at this layer; that
-- dimensional split is Gold's job (section 4.3).
--
-- Current-state upsert only, no version history (section 4.2 point 4),
-- same as Bronze: each table's UNIQUE constraint is its upsert key
-- (docs/superpowers/plans/2026-09-09-kan-34-35-36-silver-layer.md Task 1).

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE silver.hn_postings (
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

CREATE TABLE silver.yc_listings (
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

-- Fed by all staging tables together. resolved_company_key is a plain
-- resolved identity value (normalized domain, or a fuzzy-match fallback
-- key), not a foreign key into a materialized company table: Gold builds
-- the Company dimension from the distinct keys found here.
CREATE TABLE silver.resolved_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_stable_id TEXT NOT NULL,
    source TEXT NOT NULL,
    resolved_company_key TEXT NOT NULL,
    company_name_raw TEXT NOT NULL,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('hiring', 'funding', 'program_milestone', 'other')),
    stage TEXT,
    description TEXT,
    occurred_on TIMESTAMPTZ,
    url TEXT,
    key_derivation TEXT NOT NULL CHECK (key_derivation IN ('domain_normalized', 'fuzzy_matched', 'unresolved')),
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, source_stable_id)
);

CREATE TABLE silver.manual_review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resolved_signal_id UUID NOT NULL REFERENCES silver.resolved_signals (id),
    candidate_company_key TEXT NOT NULL,
    match_score NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    UNIQUE (resolved_signal_id)
);
