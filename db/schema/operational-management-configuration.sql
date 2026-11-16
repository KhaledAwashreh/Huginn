-- Additive upgrade for existing pre-management databases.
-- Run explicitly before operational-account-lifecycle.sql; never during app boot.
-- Existing accounts, users, profiles and ELT/workflow rows are preserved.
BEGIN;

CREATE TABLE IF NOT EXISTS operational.businesses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL UNIQUE REFERENCES operational.users (id) ON DELETE CASCADE,
    name TEXT CHECK (name IS NULL OR (name <> '' AND name !~ '(^[[:space:]])|([[:space:]]$)')),
    tagline TEXT CHECK (tagline IS NULL OR (tagline <> '' AND tagline !~ '(^[[:space:]])|([[:space:]]$)')),
    website TEXT CHECK (website IS NULL OR (website <> '' AND website !~ '(^[[:space:]])|([[:space:]]$)')),
    location TEXT CHECK (location IS NULL OR (location <> '' AND location !~ '(^[[:space:]])|([[:space:]]$)')),
    description TEXT CHECK (description IS NULL OR (description <> '' AND description !~ '(^[[:space:]])|([[:space:]]$)')),
    capabilities JSONB CHECK (
        capabilities IS NULL OR (
            jsonb_typeof(capabilities) = 'array'
            AND NOT jsonb_path_exists(capabilities, 'strict $[*] ? (@.type() != "object")')
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_user_id, id)
);

CREATE INDEX IF NOT EXISTS businesses_owner_user_id_idx
    ON operational.businesses (owner_user_id);

INSERT INTO operational.businesses(owner_user_id)
SELECT u.id FROM operational.users u
WHERE NOT EXISTS (
    SELECT 1 FROM operational.businesses b WHERE b.owner_user_id=u.id
);

CREATE TABLE IF NOT EXISTS operational.business_recommendation_preferences (
    business_id UUID PRIMARY KEY REFERENCES operational.businesses (id) ON DELETE CASCADE,
    repeat_interval_days INTEGER NOT NULL DEFAULT 30 CHECK (repeat_interval_days > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO operational.business_recommendation_preferences (business_id)
SELECT b.id FROM operational.businesses b
WHERE NOT EXISTS (
    SELECT 1 FROM operational.business_recommendation_preferences p
    WHERE p.business_id=b.id
);

CREATE TABLE IF NOT EXISTS operational.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES operational.accounts (id) ON DELETE NO ACTION,
    token_digest TEXT NOT NULL UNIQUE CHECK (token_digest ~ '^[0-9a-f]{64}$'),
    csrf_digest TEXT NOT NULL CHECK (csrf_digest ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS sessions_account_id_idx
    ON operational.sessions (account_id);

CREATE TABLE IF NOT EXISTS operational.service_offerings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES operational.businesses (id) ON DELETE NO ACTION,
    name TEXT NOT NULL CHECK (name <> '' AND name !~ '(^[[:space:]])|([[:space:]]$)'),
    description TEXT NOT NULL CHECK (
        description <> '' AND description !~ '(^[[:space:]])|([[:space:]]$)'
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (business_id, id)
);

CREATE INDEX IF NOT EXISTS service_offerings_business_created_idx
    ON operational.service_offerings (business_id, created_at, id);

CREATE TABLE IF NOT EXISTS operational.ideal_client_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES operational.businesses (id) ON DELETE NO ACTION,
    name TEXT NOT NULL CHECK (name <> '' AND name !~ '(^[[:space:]])|([[:space:]]$)'),
    industries JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(industries) = 'array'
        AND NOT jsonb_path_exists(industries, 'strict $[*] ? (@.type() != "object")')
    ),
    company_sizes JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(company_sizes) = 'array'
        AND NOT jsonb_path_exists(company_sizes, 'strict $[*] ? (@.type() != "object")')
        AND NOT jsonb_path_exists(
            company_sizes,
            '$[*] ? (@.band.type() == "string" && @.band != "0-10" '
            '&& @.band != "11-100" && @.band != "101-1000" && @.band != "1001+")'
        )
    ),
    geographies JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(geographies) = 'array'
        AND NOT jsonb_path_exists(geographies, 'strict $[*] ? (@.type() != "object")')
    ),
    exclusions JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(exclusions) = 'array'
        AND NOT jsonb_path_exists(exclusions, 'strict $[*] ? (@.type() != "object")')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (business_id, id)
);

CREATE INDEX IF NOT EXISTS ideal_client_profiles_business_created_idx
    ON operational.ideal_client_profiles (business_id, created_at, id);

CREATE TABLE IF NOT EXISTS operational.client_discovery_strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES operational.businesses (id) ON DELETE NO ACTION,
    name TEXT NOT NULL CHECK (name <> '' AND name !~ '(^[[:space:]])|([[:space:]]$)'),
    service_offering_id UUID NOT NULL,
    ideal_client_profile_id UUID NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (business_id, service_offering_id)
        REFERENCES operational.service_offerings (business_id, id) ON DELETE NO ACTION,
    FOREIGN KEY (business_id, ideal_client_profile_id)
        REFERENCES operational.ideal_client_profiles (business_id, id) ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS client_discovery_strategies_business_created_idx
    ON operational.client_discovery_strategies (business_id, created_at, id);

CREATE INDEX IF NOT EXISTS client_discovery_strategies_business_active_created_idx
    ON operational.client_discovery_strategies (business_id, is_active, created_at, id);

COMMIT;
