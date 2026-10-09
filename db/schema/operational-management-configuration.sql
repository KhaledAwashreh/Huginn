-- Additive upgrade for existing pre-management databases.
-- Run explicitly before operational-account-lifecycle.sql; never during app boot.
-- Existing accounts, users, profiles and ELT/workflow rows are preserved.
BEGIN;

CREATE TABLE operational.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES operational.accounts (id) ON DELETE NO ACTION,
    token_digest TEXT NOT NULL UNIQUE CHECK (token_digest ~ '^[0-9a-f]{64}$'),
    csrf_digest TEXT NOT NULL CHECK (csrf_digest ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX sessions_account_id_idx
    ON operational.sessions (account_id);

CREATE TABLE operational.service_offerings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES operational.users (id) ON DELETE NO ACTION,
    name TEXT NOT NULL CHECK (name <> '' AND name !~ '(^[[:space:]])|([[:space:]]$)'),
    description TEXT NOT NULL CHECK (
        description <> '' AND description !~ '(^[[:space:]])|([[:space:]]$)'
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, id)
);

CREATE INDEX service_offerings_user_created_idx
    ON operational.service_offerings (user_id, created_at, id);

CREATE TABLE operational.ideal_client_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES operational.users (id) ON DELETE NO ACTION,
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
    UNIQUE (user_id, id)
);

CREATE INDEX ideal_client_profiles_user_created_idx
    ON operational.ideal_client_profiles (user_id, created_at, id);

CREATE TABLE operational.client_discovery_strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES operational.users (id) ON DELETE NO ACTION,
    name TEXT NOT NULL CHECK (name <> '' AND name !~ '(^[[:space:]])|([[:space:]]$)'),
    service_offering_id UUID NOT NULL,
    ideal_client_profile_id UUID NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (user_id, service_offering_id)
        REFERENCES operational.service_offerings (user_id, id) ON DELETE NO ACTION,
    FOREIGN KEY (user_id, ideal_client_profile_id)
        REFERENCES operational.ideal_client_profiles (user_id, id) ON DELETE NO ACTION
);

CREATE INDEX client_discovery_strategies_user_created_idx
    ON operational.client_discovery_strategies (user_id, created_at, id);

CREATE INDEX client_discovery_strategies_user_active_created_idx
    ON operational.client_discovery_strategies (user_id, is_active, created_at, id);

COMMIT;
