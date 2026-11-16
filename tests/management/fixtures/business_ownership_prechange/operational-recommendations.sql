-- Explicit additive recommendation history setup, never applied by app startup.
BEGIN;
CREATE TABLE IF NOT EXISTS operational.recommendation_batches (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES operational.users(id),
    -- Retain the original identity even after its mutable configuration is deleted.
    strategy_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    snapshot JSONB NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    UNIQUE (id, user_id)
);
CREATE INDEX IF NOT EXISTS recommendation_batches_owner_strategy_created_idx
    ON operational.recommendation_batches(user_id, strategy_id, created_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS operational.recommendation_feedback (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    batch_id UUID NOT NULL,
    recommendation_id TEXT NOT NULL CHECK (recommendation_id <> ''),
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (batch_id, user_id) REFERENCES operational.recommendation_batches(id, user_id)
);
CREATE INDEX IF NOT EXISTS recommendation_feedback_batch_owner_created_idx
    ON operational.recommendation_feedback(batch_id, user_id, created_at, id);
CREATE OR REPLACE FUNCTION operational.reject_recommendation_history_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'recommendation history is immutable' USING ERRCODE = '55000';
END $$;
DROP TRIGGER IF EXISTS recommendation_batches_immutable ON operational.recommendation_batches;
CREATE TRIGGER recommendation_batches_immutable BEFORE UPDATE OR DELETE
    ON operational.recommendation_batches FOR EACH ROW
    EXECUTE FUNCTION operational.reject_recommendation_history_mutation();
DROP TRIGGER IF EXISTS recommendation_feedback_immutable ON operational.recommendation_feedback;
CREATE TRIGGER recommendation_feedback_immutable BEFORE UPDATE OR DELETE
    ON operational.recommendation_feedback FOR EACH ROW
    EXECUTE FUNCTION operational.reject_recommendation_history_mutation();
CREATE OR REPLACE FUNCTION operational.validate_recommendation_feedback_occurrence()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM operational.recommendation_batches AS b,
            LATERAL jsonb_array_elements(b.snapshot->'batch'->'items') AS item
        WHERE b.id = NEW.batch_id AND b.user_id = NEW.user_id
          AND item->>'id' = NEW.recommendation_id
    ) THEN
        RAISE EXCEPTION 'recommendation occurrence not found in owned batch' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS recommendation_feedback_occurrence ON operational.recommendation_feedback;
CREATE TRIGGER recommendation_feedback_occurrence BEFORE INSERT
    ON operational.recommendation_feedback FOR EACH ROW
    EXECUTE FUNCTION operational.validate_recommendation_feedback_occurrence();
COMMIT;
