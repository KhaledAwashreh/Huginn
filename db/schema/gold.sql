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
    -- Funding/development stage as the source classifies it. Free text,
    -- not an enum: YC supplies 'Early'/'Growth' but a second source may
    -- use its own vocabulary, and constraining here would force a
    -- translation table before a second source exists. Type 1 for now;
    -- whether a stage transition should write CompanyHistory is part of
    -- the open column classification (Jira KAN-20).
    stage TEXT,
    -- Registry lifecycle status, free text as the source spells it: YC
    -- supplies 'Active', 'Inactive', 'Acquired', 'Public'. Constraining
    -- here would bake one registry's vocabulary into the schema before a
    -- second registry exists, the same reasoning as stage above. A
    -- distinct axis from company_type (legal form) and from
    -- company_scale (size). YC's vocabulary is Active/Inactive/Acquired/
    -- Public, but Acquired and Inactive are filtered out before Silver, so
    -- in practice this holds 'Active', 'Public', or NULL for a company only
    -- an HN signal knows about. Type 1 for now, on the same open-question
    -- footing as stage and company_scale: an Active-to-Public transition is
    -- a real lifecycle change with no history column to record it, and
    -- whether it should write one is part of KAN-20.
    company_status TEXT,
    -- Sector classification, an array because a company legitimately sits in
    -- more than one (verified live: 4,899 of 6,252 YC rows report more than
    -- one industry). Collapsing that list to one value would discard source
    -- information to fit a scalar, and 'startup'-style flattening was exactly
    -- the vocabulary mistake already rejected for company_scale. Values are
    -- YC's own strings, untranslated, including the literal 'Unspecified':
    -- a company Huginn cannot classify yet is more honestly recorded as
    -- unknown than assigned a guess, and a second source may fill it later.
    -- Type 2 tracked (see gold.company_history).
    business_sector TEXT[],
    -- Size/structure bucket, derived from a headcount signal such as YC's
    -- `team_size`. Constrained, and the constraint is the four headcount
    -- bands rather than a looser 'enterprise'/'startup'/'sme' vocabulary,
    -- because headcount is objective and reproducible. 'startup' would
    -- match 100% of a YC-sourced directory and so carry no information,
    -- and it collides with the separate `stage` column above. The bands
    -- are Huginn's own, no source supplies them directly, which is what
    -- makes constraining them here legitimate. The lowest band includes
    -- team_size=0: confirmed live that 133 YC rows report 0 with a
    -- populated batch, industry, and often a one-liner, and 41 of them
    -- are Active, so it reads as pre-first-hire rather than missing data.
    company_scale TEXT CHECK (company_scale IN ('0-10', '11-100', '101-1000', '1001+')),
    -- Free-text notes about the company, each opening with the source that
    -- supplied the value, e.g. 'YC Summer 2023'. One column rather
    -- than one per source per fact: a second portal's batch, founding year,
    -- or registry field is inevitable, and a column per fact per source does
    -- not scale. The prefix is what keeps a reader able to tell whose
    -- statement it is. Type 1, no company_history counterpart: a note is
    -- descriptive, so a change in wording is not a recorded attribute
    -- change. Values are composed in Gold, not captured in Silver, because
    -- the prefix is Huginn's vocabulary (section 4.3).
    notes TEXT,
    -- Legal form, free text: "Private Limited Company", "LLC", "C Corp".
    -- Deliberately NOT the same axis as company_scale. OpenCorporates
    -- supplies a legal form here and a headcount-derived size is a
    -- different measurement; mapping one onto the other silently
    -- corrupts the column (architecture-notes/opencorporates-fetch-plan.md
    -- section 4). Unconstrained because legal forms are jurisdiction
    -- specific and unbounded.
    company_type TEXT,
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
    business_sector TEXT[],
    team_composition_signal TEXT NOT NULL CHECK (team_composition_signal IN ('unknown', 'likely_no', 'likely_yes')),
    icp_filter_pass BOOLEAN NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ NOT NULL
);

-- (source, source_stable_id) is silver.resolved_signals's own natural key,
-- reused here so a re-run of Silver's every-run reprocessing (see that
-- table's own comment) upserts the same fact row instead of duplicating it.
-- See ADR-0007.
CREATE TABLE gold.company_signal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES gold.company (id),
    source TEXT NOT NULL,
    source_stable_id TEXT NOT NULL,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('funding', 'hiring', 'program_milestone', 'expansion', 'leadership', 'other')),
    source_url TEXT,
    stage TEXT,
    description TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, source_stable_id)
);
