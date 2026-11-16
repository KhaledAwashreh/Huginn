-- Explicit operator-applied setup; never applied during application startup.
BEGIN;
CREATE TABLE IF NOT EXISTS operational.weekly_digest_subscriptions (
    business_id UUID PRIMARY KEY REFERENCES operational.businesses(id),
    enabled BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL
);
-- Existing opt-ins now cover all valid active strategies; preserve consent.
ALTER TABLE operational.weekly_digest_subscriptions DROP COLUMN IF EXISTS strategy_id;
CREATE TABLE IF NOT EXISTS operational.weekly_digest_deliveries (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL REFERENCES operational.businesses(id),
    recipient_user_id UUID NOT NULL,
    week_start DATE NOT NULL CHECK (extract(isodow FROM week_start) = 1),
    created_at TIMESTAMPTZ NOT NULL,
    settled_at TIMESTAMPTZ,
    state TEXT NOT NULL DEFAULT 'preparing' CHECK (state IN ('preparing','sending','sent','unknown','empty','failed','suppressed')),
    batch_id UUID,
    recipient TEXT,
    subject TEXT,
    body TEXT,
    company_ids JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(company_ids) = 'array'),
    UNIQUE (business_id, week_start),
    CONSTRAINT weekly_digest_deliveries_recipient_user_fkey
        FOREIGN KEY (recipient_user_id) REFERENCES operational.users(id) ON DELETE NO ACTION,
    CONSTRAINT weekly_digest_deliveries_business_recipient_fkey
        FOREIGN KEY (recipient_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION,
    CONSTRAINT weekly_digest_deliveries_batch_recipient_fkey
        FOREIGN KEY (batch_id,recipient_user_id)
        REFERENCES operational.recommendation_batches(id,user_id),
    CHECK (state NOT IN ('sending','sent','unknown') OR
        (batch_id IS NOT NULL AND recipient IS NOT NULL AND subject IS NOT NULL AND body IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS weekly_digest_deliveries_created_idx
    ON operational.weekly_digest_deliveries(created_at);
COMMIT;
