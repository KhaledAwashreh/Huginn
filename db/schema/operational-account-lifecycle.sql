-- Explicit additive operator migration; boot never applies this file.
-- Run with ON_ERROR_STOP; this file owns its transaction, including backfill.
BEGIN;

-- Prevent account writes from racing the trusted legacy snapshot. New writers
-- must already create explicit recovery identity rows in their transaction.
LOCK TABLE operational.accounts IN SHARE ROW EXCLUSIVE MODE;

-- Public-account lifecycle storage. See openspec/changes/public-account-lifecycle/design.md.
CREATE TABLE IF NOT EXISTS operational.account_recovery_identity (
    account_id UUID PRIMARY KEY REFERENCES operational.accounts (id),
    verification_required BOOLEAN NOT NULL,
    pending_email TEXT CHECK (pending_email <> '' AND pending_email !~ '(^[[:space:]])|([[:space:]]$)'),
    verified_email TEXT CHECK (verified_email <> '' AND verified_email !~ '(^[[:space:]])|([[:space:]]$)'),
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((verified_email IS NULL) = (verified_at IS NULL)),
    CONSTRAINT account_recovery_identity_check1
        CHECK (pending_email IS NULL OR verified_email IS NULL),
    CONSTRAINT account_recovery_identity_required_address_check
        CHECK (NOT verification_required OR pending_email IS NOT NULL OR verified_email IS NOT NULL)
);

-- Fail without changing legacy rows; operators must resolve ownership explicitly.
LOCK TABLE operational.users IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM operational.users GROUP BY lower(btrim(email)) HAVING count(*) > 1)
       OR EXISTS (
           SELECT 1 FROM operational.account_recovery_identity r
           CROSS JOIN LATERAL unnest(ARRAY[r.pending_email, r.verified_email]) AS addresses(email)
           WHERE email IS NOT NULL GROUP BY lower(btrim(email)) HAVING count(*) > 1
       ) THEN
        RAISE EXCEPTION 'Duplicate account emails prevent migration. Resolve case-insensitive contact and recovery email ownership explicitly, then rerun. No rows were merged, deleted, or verified.';
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key
    ON operational.users (lower(btrim(email)));

-- Replace the legacy mutually exclusive address check and coalesced index.
ALTER TABLE operational.account_recovery_identity
    DROP CONSTRAINT IF EXISTS account_recovery_identity_check1,
    DROP CONSTRAINT IF EXISTS account_recovery_identity_distinct_emails_check,
    ADD CONSTRAINT account_recovery_identity_distinct_emails_check
        CHECK (lower(btrim(pending_email)) <> lower(btrim(verified_email)));

DROP INDEX IF EXISTS operational.account_recovery_identity_email_lower_key;
CREATE UNIQUE INDEX account_recovery_identity_email_lower_key
    ON operational.account_recovery_identity (lower(btrim(pending_email)));

CREATE UNIQUE INDEX IF NOT EXISTS account_recovery_identity_verified_email_lower_key
    ON operational.account_recovery_identity (lower(btrim(verified_email)));

CREATE OR REPLACE FUNCTION operational.reserve_account_recovery_addresses()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    claimed_email TEXT;
BEGIN
    FOR claimed_email IN
        SELECT DISTINCT lower(btrim(address))
        FROM unnest(ARRAY[NEW.pending_email, NEW.verified_email]) AS addresses(address)
        WHERE address IS NOT NULL
        ORDER BY 1
    LOOP
        -- Promoting an existing pending address retains its reservation.
        IF TG_OP = 'UPDATE' AND (
            claimed_email = lower(btrim(OLD.pending_email))
            OR claimed_email = lower(btrim(OLD.verified_email))
        ) THEN
            CONTINUE;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(claimed_email, 14931));
        IF EXISTS (
            SELECT 1 FROM operational.account_recovery_identity r
            WHERE r.account_id <> NEW.account_id
              AND (lower(btrim(r.pending_email)) = claimed_email
                   OR lower(btrim(r.verified_email)) = claimed_email)
        ) OR EXISTS (
            SELECT 1 FROM operational.users u
            WHERE u.account_id <> NEW.account_id AND lower(btrim(u.email)) = claimed_email
        ) THEN
            RAISE unique_violation USING
                MESSAGE = 'Account email is already in use',
                CONSTRAINT = 'account_recovery_identity_email_lower_key';
        END IF;
    END LOOP;
    RETURN NEW;
END $$;

CREATE OR REPLACE TRIGGER account_recovery_identity_reserve_addresses
    BEFORE INSERT OR UPDATE OF pending_email, verified_email ON operational.account_recovery_identity
    FOR EACH ROW EXECUTE FUNCTION operational.reserve_account_recovery_addresses();

CREATE TABLE IF NOT EXISTS operational.account_lifecycle_proofs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES operational.accounts (id),
    token_digest TEXT NOT NULL UNIQUE CHECK (token_digest ~ '^[0-9a-f]{64}$'),
    purpose TEXT NOT NULL CHECK (purpose IN ('verify_email', 'reset_password')),
    destination TEXT NOT NULL CHECK (destination <> '' AND destination !~ '(^[[:space:]])|([[:space:]]$)'),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    superseded BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, account_id, purpose),
    CHECK (expires_at > created_at),
    CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX IF NOT EXISTS account_lifecycle_proofs_account_purpose_idx
    ON operational.account_lifecycle_proofs (account_id, purpose, created_at);

-- The authenticated ciphertext envelope holds both recipient snapshot and token.
-- Terminal rows retain safe metadata only; claim ownership fences stale settlement.
CREATE TABLE IF NOT EXISTS operational.lifecycle_mail_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES operational.accounts (id),
    proof_id UUID NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('verify_email', 'reset_password')),
    encrypted_payload BYTEA,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 5),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'claimed', 'sent', 'failed', 'suppressed')),
    failure_code TEXT CHECK (failure_code IN (
        'transport_unavailable', 'attempts_exhausted', 'obsolete_proof',
        'expired_proof', 'invalid_payload'
    )),
    claim_token UUID,
    claimed_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (proof_id, account_id, purpose)
        REFERENCES operational.account_lifecycle_proofs (id, account_id, purpose),
    CHECK (
        (state IN ('pending', 'claimed') AND encrypted_payload IS NOT NULL AND octet_length(encrypted_payload) > 0)
        OR (state IN ('sent', 'failed', 'suppressed') AND encrypted_payload IS NULL)
    ),
    CHECK (
        (state = 'claimed' AND claim_token IS NOT NULL AND claimed_at IS NOT NULL
            AND lease_until IS NOT NULL AND lease_until > claimed_at AND attempt_count > 0)
        OR (state <> 'claimed' AND claim_token IS NULL AND claimed_at IS NULL AND lease_until IS NULL)
    ),
    CHECK ((state = 'sent') = (sent_at IS NOT NULL)),
    CHECK (state <> 'pending' OR attempt_count < 5)
);

CREATE INDEX IF NOT EXISTS lifecycle_mail_outbox_due_idx
    ON operational.lifecycle_mail_outbox (next_attempt_at, id) WHERE state = 'pending';
CREATE INDEX IF NOT EXISTS lifecycle_mail_outbox_lease_idx
    ON operational.lifecycle_mail_outbox (lease_until, id) WHERE state = 'claimed';
CREATE INDEX IF NOT EXISTS lifecycle_mail_outbox_account_created_idx
    ON operational.lifecycle_mail_outbox (account_id, created_at);

-- Digests only: public throttling never persists a submitted username or raw IP.
CREATE TABLE IF NOT EXISTS operational.lifecycle_throttle (
    scope TEXT NOT NULL CHECK (scope IN ('receipt_username', 'receipt_email', 'receipt_ip', 'proof_ip')),
    key_digest TEXT NOT NULL CHECK (key_digest ~ '^[0-9a-f]{64}$'),
    window_started_at TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, key_digest)
);

-- Extend the old scope constraint without discarding throttle history.
ALTER TABLE operational.lifecycle_throttle DROP CONSTRAINT IF EXISTS lifecycle_throttle_scope_check;
ALTER TABLE operational.lifecycle_throttle ADD CONSTRAINT lifecycle_throttle_scope_check
    CHECK (scope IN ('receipt_username', 'receipt_email', 'receipt_ip', 'proof_ip'));

-- Never infer recovery ownership from contact email, or overwrite public rows.
INSERT INTO operational.account_recovery_identity (account_id, verification_required)
SELECT id, false FROM operational.accounts
ON CONFLICT (account_id) DO NOTHING;

COMMIT;
