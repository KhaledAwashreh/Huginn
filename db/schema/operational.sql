-- Operational schema: written by the matching step, not by the ELT
-- pipeline. See architecture document section 9 and docs/entities.md.
--
-- `users` is not in docs/entities.md's current sketch (only referenced via
-- Match.UserId and the "icp_profile" label in the architecture document's
-- data model diagram). Included here minimally so the foreign key below
-- is valid; revisit alongside the ICP capture flow (architecture document
-- section 11, open item, not yet tracked).

CREATE SCHEMA IF NOT EXISTS operational;

CREATE TABLE operational.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    icp_profile JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operational.employee (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES gold.company (id),
    name TEXT NOT NULL,
    position TEXT,
    phone_number TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operational.match (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES operational.users (id),
    company_id UUID NOT NULL REFERENCES gold.company (id),
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'responded', 'dismissed', 'converted')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A single row per match today. Section 7's recompute design needs this
-- to grow into a versioned history before v1 scoring ships (Jira KAN-8).
CREATE TABLE operational.match_score (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id UUID NOT NULL REFERENCES operational.match (id),
    scoring_algorithm TEXT NOT NULL,
    score INTEGER NOT NULL,
    feature_breakdown JSONB,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operational.match_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id UUID NOT NULL REFERENCES operational.match (id),
    rating TEXT NOT NULL CHECK (rating IN ('positive', 'negative')),
    given_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- `type` is intentionally unconstrained: docs/entities.md leaves this list
-- open-ended (Note, EmailSent, CallMade, FollowUpPlanned, and so on).
CREATE TABLE operational.activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id UUID NOT NULL REFERENCES operational.match (id),
    employee_id UUID REFERENCES operational.employee (id),
    type TEXT NOT NULL,
    due_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    notes TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operational.communication (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id UUID NOT NULL REFERENCES operational.match (id),
    channel TEXT NOT NULL CHECK (channel IN ('email', 'linkedin', 'other')),
    subject TEXT,
    status TEXT NOT NULL DEFAULT 'drafting' CHECK (status IN ('drafting', 'finalized', 'sent')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operational.communication_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    communication_id UUID NOT NULL REFERENCES operational.communication (id),
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    is_final BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operational.communication_revision (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    communication_version_id UUID NOT NULL REFERENCES operational.communication_version (id),
    derived_from_version_id UUID REFERENCES operational.communication_version (id),
    agent_type TEXT NOT NULL CHECK (agent_type IN ('user', 'ai')),
    change_summary TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operational.communication_turn (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    communication_revision_id UUID NOT NULL REFERENCES operational.communication_revision (id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
