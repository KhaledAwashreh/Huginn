-- Gold layer: dimensional model over Silver's resolved signals.
-- See architecture document section 4.3, ADR-0002, and docs/entities.md.
--
-- Company holds exactly one row per company, always, overwritten in
-- place. CompanyHistory gets a new row only when a Type 2 tracked field
-- changes (business_sector, team_composition_signal, icp_filter_pass;
-- see src/huginn/gold/dimensional.py TYPE_2_TRACKED_FIELDS). This is a
-- current-plus-history split, not a single SCD Type 2 table (ADR-0002):
-- every scoring read needs current state, and this design removes the
-- IsCurrent-filter risk from that read entirely.

CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE gold.company (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    business_sector TEXT,
    company_type TEXT CHECK (company_type IN ('enterprise', 'startup', 'sme')),
    country TEXT,
    city TEXT,
    address TEXT,
    phone_number TEXT,
    email TEXT,
    team_composition_signal TEXT NOT NULL DEFAULT 'unknown' CHECK (team_composition_signal IN ('unknown', 'likely_no', 'likely_yes')),
    icp_filter_pass BOOLEAN NOT NULL DEFAULT false,
    current_since TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per superseded version. Nothing here is ever current by
-- definition, so there is no is_current flag, only the closed
-- valid_from/valid_to window (ADR-0002).
CREATE TABLE gold.company_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES gold.company (id),
    domain TEXT NOT NULL,
    business_sector TEXT,
    team_composition_signal TEXT NOT NULL CHECK (team_composition_signal IN ('unknown', 'likely_no', 'likely_yes')),
    icp_filter_pass BOOLEAN NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ NOT NULL
);

CREATE TABLE gold.company_signal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES gold.company (id),
    signal_type TEXT NOT NULL CHECK (signal_type IN ('funding', 'hiring', 'program_milestone', 'expansion', 'leadership', 'other')),
    source TEXT NOT NULL,
    source_url TEXT,
    stage TEXT,
    description TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
