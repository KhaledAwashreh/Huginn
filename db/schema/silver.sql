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

-- YC-specific columns. HN's "Who's Hiring" comments carry no registry
-- status and no headcount, so these do not exist on silver.hn_postings.
-- ADR-0001 anticipated exactly this: "a future source-specific staging
-- column can be added to just that source's table, without an ALTER
-- TABLE or a meaningless nullable column on every other table."
-- team_size stays a raw integer here, not a band: the band vocabulary is
-- Huginn's own, so the bucketing is Gold's job (section 4.3).
CREATE TABLE silver.yc_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stable_id TEXT NOT NULL,
    company_name_raw TEXT NOT NULL,
    website TEXT,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('hiring', 'funding', 'program_milestone', 'other')),
    stage TEXT,
    company_status TEXT,
    team_size INTEGER,
    -- YC's `industries` verbatim: a list on 78% of live rows, singular
    -- `industry` is always its first element, so this is a strict superset
    -- and `industry` is not stored separately. Source's own vocabulary,
    -- untranslated, including the literal 'Unspecified'.
    industries TEXT[],
    -- YC's `all_locations` verbatim, e.g. 'San Francisco, CA, USA; Remote'.
    -- Kept as the source's display string rather than split here: it is a
    -- human-facing field with no guaranteed structure, so the parse into
    -- Gold's country/city is Gold's interpretation to own (section 4.3).
    all_locations TEXT,
    -- YC's `former_names` verbatim, on 3,054 of 6,252 live rows. Not
    -- cleaned: entries include case variants of the current name and
    -- self-referential ones, e.g. ['Imgix', 'imgix']. Captured because
    -- Silver owns faithful capture, and read by nothing yet: recall needs
    -- name-based matching, which is Jira KAN-4.
    former_names TEXT[],
    -- YC's `batch` verbatim, e.g. 'Winter 2022': the funded batch the
    -- company joined YC in. Deliberately not derived from occurred_on,
    -- which carries YC's unrelated `launched_at`. 51 distinct live values
    -- plus one 'Unspecified'. See db/schema/silver-yc-batch.sql for the
    -- evidence that the two dates are independent.
    batch TEXT,
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
    -- Cross-source table, so unlike the per-source staging tables these are
    -- YC-shaped by circumstance rather than by design: an HN row has no
    -- registry status and no headcount, so all of them are NULL for it.
    -- Gold treats a NULL here as "this source does not know", never as a
    -- value that clears one an earlier source supplied.
    company_status TEXT,
    team_size INTEGER,
    industries TEXT[],
    all_locations TEXT,
    former_names TEXT[],
    -- YC's funded batch, verbatim. See silver.yc_listings.batch.
    batch TEXT,
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
