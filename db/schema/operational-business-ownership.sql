-- Explicit, repeatable ownership setup for existing management databases.
-- Inspect the target and read preserved rows back before enabling new writers.
-- Never run during application startup.
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

-- Existing Business IDs and fields win. Missing Users alone receive a Business.
INSERT INTO operational.businesses(owner_user_id)
SELECT u.id FROM operational.users u
ON CONFLICT (owner_user_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS operational.business_recommendation_preferences (
    business_id UUID PRIMARY KEY REFERENCES operational.businesses (id) ON DELETE CASCADE,
    repeat_interval_days INTEGER NOT NULL DEFAULT 30 CHECK (repeat_interval_days > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Do not reset a configured interval when setup is repeated.
INSERT INTO operational.business_recommendation_preferences (business_id)
SELECT id FROM operational.businesses
ON CONFLICT (business_id) DO NOTHING;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    -- Legacy strategy references depend on the config tables' old unique keys.
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='operational' AND table_name='client_discovery_strategies'
          AND column_name='user_id'
    ) THEN
        FOR constraint_name IN
            SELECT conname FROM pg_constraint
            WHERE conrelid='operational.client_discovery_strategies'::regclass
              AND contype='f'
              AND pg_get_constraintdef(oid) LIKE 'FOREIGN KEY (user_id, %'
        LOOP
            EXECUTE format(
                'ALTER TABLE operational.client_discovery_strategies DROP CONSTRAINT %I',
                constraint_name
            );
        END LOOP;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='operational' AND table_name='service_offerings'
          AND column_name='user_id'
    ) THEN
        ALTER TABLE operational.service_offerings ADD COLUMN business_id UUID;
        UPDATE operational.service_offerings offering
        SET business_id=business.id
        FROM operational.businesses business
        WHERE business.owner_user_id=offering.user_id
          AND offering.business_id IS NULL;
        ALTER TABLE operational.service_offerings ALTER COLUMN business_id SET NOT NULL;
        ALTER TABLE operational.service_offerings
            DROP CONSTRAINT IF EXISTS service_offerings_user_id_fkey,
            DROP CONSTRAINT IF EXISTS service_offerings_user_id_id_key;
        DROP INDEX IF EXISTS operational.service_offerings_user_created_idx;
        ALTER TABLE operational.service_offerings DROP COLUMN user_id;
        ALTER TABLE operational.service_offerings
            ADD CONSTRAINT service_offerings_business_id_fkey
                FOREIGN KEY (business_id) REFERENCES operational.businesses(id) ON DELETE NO ACTION,
            ADD CONSTRAINT service_offerings_business_id_id_key UNIQUE (business_id,id);
        CREATE INDEX IF NOT EXISTS service_offerings_business_created_idx
            ON operational.service_offerings (business_id, created_at, id);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='operational' AND table_name='ideal_client_profiles'
          AND column_name='user_id'
    ) THEN
        ALTER TABLE operational.ideal_client_profiles ADD COLUMN business_id UUID;
        UPDATE operational.ideal_client_profiles profile
        SET business_id=business.id
        FROM operational.businesses business
        WHERE business.owner_user_id=profile.user_id
          AND profile.business_id IS NULL;
        ALTER TABLE operational.ideal_client_profiles ALTER COLUMN business_id SET NOT NULL;
        ALTER TABLE operational.ideal_client_profiles
            DROP CONSTRAINT IF EXISTS ideal_client_profiles_user_id_fkey,
            DROP CONSTRAINT IF EXISTS ideal_client_profiles_user_id_id_key;
        DROP INDEX IF EXISTS operational.ideal_client_profiles_user_created_idx;
        ALTER TABLE operational.ideal_client_profiles DROP COLUMN user_id;
        ALTER TABLE operational.ideal_client_profiles
            ADD CONSTRAINT ideal_client_profiles_business_id_fkey
                FOREIGN KEY (business_id) REFERENCES operational.businesses(id) ON DELETE NO ACTION,
            ADD CONSTRAINT ideal_client_profiles_business_id_id_key UNIQUE (business_id,id);
        CREATE INDEX IF NOT EXISTS ideal_client_profiles_business_created_idx
            ON operational.ideal_client_profiles (business_id, created_at, id);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='operational' AND table_name='client_discovery_strategies'
          AND column_name='user_id'
    ) THEN
        ALTER TABLE operational.client_discovery_strategies ADD COLUMN business_id UUID;
        UPDATE operational.client_discovery_strategies strategy
        SET business_id=business.id
        FROM operational.businesses business
        WHERE business.owner_user_id=strategy.user_id
          AND strategy.business_id IS NULL;
        ALTER TABLE operational.client_discovery_strategies ALTER COLUMN business_id SET NOT NULL;
        ALTER TABLE operational.client_discovery_strategies
            DROP CONSTRAINT IF EXISTS client_discovery_strategies_user_id_fkey;
        DROP INDEX IF EXISTS operational.client_discovery_strategies_user_created_idx;
        DROP INDEX IF EXISTS operational.client_discovery_strategies_user_active_created_idx;
        ALTER TABLE operational.client_discovery_strategies DROP COLUMN user_id;
        ALTER TABLE operational.client_discovery_strategies
            ADD CONSTRAINT client_discovery_strategies_business_id_fkey
                FOREIGN KEY (business_id) REFERENCES operational.businesses(id) ON DELETE NO ACTION,
            ADD CONSTRAINT client_discovery_strategies_business_offering_fkey
                FOREIGN KEY (business_id, service_offering_id)
                REFERENCES operational.service_offerings(business_id,id) ON DELETE NO ACTION,
            ADD CONSTRAINT client_discovery_strategies_business_profile_fkey
                FOREIGN KEY (business_id, ideal_client_profile_id)
                REFERENCES operational.ideal_client_profiles(business_id,id) ON DELETE NO ACTION;
        CREATE INDEX IF NOT EXISTS client_discovery_strategies_business_created_idx
            ON operational.client_discovery_strategies (business_id, created_at, id);
        CREATE INDEX IF NOT EXISTS client_discovery_strategies_business_active_created_idx
            ON operational.client_discovery_strategies (business_id, is_active, created_at, id);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='operational' AND table_name='weekly_digest_subscriptions'
          AND column_name='user_id'
    ) THEN
        ALTER TABLE operational.weekly_digest_subscriptions ADD COLUMN business_id UUID;
        UPDATE operational.weekly_digest_subscriptions subscription
        SET business_id=business.id
        FROM operational.businesses business
        WHERE business.owner_user_id=subscription.user_id
          AND subscription.business_id IS NULL;
        ALTER TABLE operational.weekly_digest_subscriptions ALTER COLUMN business_id SET NOT NULL;
        ALTER TABLE operational.weekly_digest_subscriptions
            DROP CONSTRAINT IF EXISTS weekly_digest_subscriptions_pkey,
            DROP CONSTRAINT IF EXISTS weekly_digest_subscriptions_user_id_fkey;
        ALTER TABLE operational.weekly_digest_subscriptions DROP COLUMN user_id;
        ALTER TABLE operational.weekly_digest_subscriptions
            ADD CONSTRAINT weekly_digest_subscriptions_pkey PRIMARY KEY (business_id),
            ADD CONSTRAINT weekly_digest_subscriptions_business_id_fkey
                FOREIGN KEY (business_id) REFERENCES operational.businesses(id) ON DELETE NO ACTION;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='operational' AND table_name='weekly_digest_deliveries'
          AND column_name='user_id'
    ) THEN
        ALTER TABLE operational.weekly_digest_deliveries ADD COLUMN business_id UUID;
        UPDATE operational.weekly_digest_deliveries delivery
        SET business_id=business.id
        FROM operational.businesses business
        WHERE business.owner_user_id=delivery.user_id
          AND delivery.business_id IS NULL;
        ALTER TABLE operational.weekly_digest_deliveries ALTER COLUMN business_id SET NOT NULL;
        ALTER TABLE operational.weekly_digest_deliveries
            DROP CONSTRAINT IF EXISTS weekly_digest_deliveries_user_id_fkey,
            DROP CONSTRAINT IF EXISTS weekly_digest_deliveries_user_id_week_start_key,
            DROP CONSTRAINT IF EXISTS weekly_digest_deliveries_batch_id_user_id_fkey;
        ALTER TABLE operational.weekly_digest_deliveries RENAME COLUMN user_id TO recipient_user_id;
        ALTER TABLE operational.weekly_digest_deliveries
            ADD CONSTRAINT weekly_digest_deliveries_business_id_fkey
                FOREIGN KEY (business_id) REFERENCES operational.businesses(id) ON DELETE NO ACTION,
            ADD CONSTRAINT weekly_digest_deliveries_business_week_start_key
                UNIQUE (business_id, week_start);
    END IF;

    -- Enforce both recipient existence and that the recipient owns this Business.
    IF to_regclass('operational.weekly_digest_deliveries') IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid='operational.weekly_digest_deliveries'::regclass
              AND conname='weekly_digest_deliveries_recipient_user_fkey'
        ) THEN
            ALTER TABLE operational.weekly_digest_deliveries
                ADD CONSTRAINT weekly_digest_deliveries_recipient_user_fkey
                FOREIGN KEY (recipient_user_id) REFERENCES operational.users(id) ON DELETE NO ACTION;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid='operational.weekly_digest_deliveries'::regclass
              AND conname='weekly_digest_deliveries_business_recipient_fkey'
        ) THEN
            ALTER TABLE operational.weekly_digest_deliveries
                ADD CONSTRAINT weekly_digest_deliveries_business_recipient_fkey
                FOREIGN KEY (recipient_user_id,business_id)
                REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION;
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid='operational.weekly_digest_deliveries'::regclass
              AND attname='batch_id' AND NOT attisdropped
        ) AND NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid='operational.weekly_digest_deliveries'::regclass
              AND conname='weekly_digest_deliveries_batch_recipient_fkey'
        ) THEN
            ALTER TABLE operational.weekly_digest_deliveries
                ADD CONSTRAINT weekly_digest_deliveries_batch_recipient_fkey
                FOREIGN KEY (batch_id,recipient_user_id)
                REFERENCES operational.recommendation_batches(id,user_id);
        END IF;
    END IF;
END $$;

COMMIT;
