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
    CHECK (pending_email IS NULL OR verified_email IS NULL),
    CHECK (NOT verification_required OR pending_email IS NOT NULL OR verified_email IS NOT NULL)
);

-- Fail without changing legacy rows; operators must resolve ownership explicitly.
LOCK TABLE operational.users IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM operational.users GROUP BY lower(btrim(email)) HAVING count(*) > 1)
       OR EXISTS (SELECT 1 FROM operational.account_recovery_identity
           WHERE COALESCE(pending_email, verified_email) IS NOT NULL
           GROUP BY lower(btrim(COALESCE(pending_email, verified_email))) HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Duplicate account emails prevent migration. Resolve case-insensitive contact and recovery email ownership explicitly, then rerun. No rows were merged, deleted, or verified.';
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key
    ON operational.users (lower(btrim(email)));

CREATE UNIQUE INDEX IF NOT EXISTS account_recovery_identity_email_lower_key
    ON operational.account_recovery_identity (lower(btrim(COALESCE(pending_email, verified_email))));

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
