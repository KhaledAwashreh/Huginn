-- Explicit schema setup for Business-owned recommendation and prospect history.
-- Never apply during application startup; see ADR-0019.
BEGIN;

CREATE TABLE IF NOT EXISTS operational.recommendations (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL,
    company_id UUID NOT NULL REFERENCES gold.company(id) ON DELETE NO ACTION,
    status TEXT NOT NULL CHECK (status IN ('open','converted','rejected')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    current_revision_id UUID,
    first_presented_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolved_by_user_id UUID,
    resolution_reason TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    CONSTRAINT recommendations_business_fkey
        FOREIGN KEY (business_id) REFERENCES operational.businesses(id) ON DELETE NO ACTION,
    CONSTRAINT recommendations_id_business_company_key
        UNIQUE (id,business_id,company_id),
    CONSTRAINT recommendations_id_business_key UNIQUE (id,business_id),
    CONSTRAINT recommendations_business_owner_fkey
        FOREIGN KEY (resolved_by_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION,
    CHECK ((status='open') = (resolved_at IS NULL)),
    CHECK ((status='open') = (resolved_by_user_id IS NULL)),
    CHECK (status='open' OR resolved_at IS NOT NULL),
    CHECK (status='open' OR resolved_by_user_id IS NOT NULL),
    CHECK (status<>'open' OR resolution_reason IS NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS recommendations_one_open_business_company_idx
    ON operational.recommendations (business_id,company_id) WHERE status='open';
CREATE INDEX IF NOT EXISTS recommendations_business_status_updated_idx
    ON operational.recommendations (business_id,status,updated_at DESC,id DESC);

CREATE TABLE IF NOT EXISTS operational.assessment_revisions (
    id UUID PRIMARY KEY,
    recommendation_id UUID NOT NULL,
    business_id UUID NOT NULL,
    company_id UUID NOT NULL,
    revision_number INTEGER NOT NULL CHECK (revision_number > 0),
    assessed_at TIMESTAMPTZ NOT NULL,
    strategy_assessments JSONB NOT NULL CHECK (
        jsonb_typeof(strategy_assessments)='array' AND jsonb_array_length(strategy_assessments)>0
    ),
    professional_profile_snapshot JSONB NOT NULL CHECK (
        jsonb_typeof(professional_profile_snapshot)='object'
    ),
    evidence_snapshots JSONB NOT NULL CHECK (jsonb_typeof(evidence_snapshots)='array'),
    evidence_observation_ids UUID[] NOT NULL,
    policy_versions TEXT[] NOT NULL CHECK (cardinality(policy_versions)>0),
    evaluation_seed TEXT,
    assessed_by_user_id UUID,
    CONSTRAINT assessment_revisions_recommendation_fkey
        FOREIGN KEY (recommendation_id,business_id,company_id)
        REFERENCES operational.recommendations(id,business_id,company_id) ON DELETE NO ACTION,
    CONSTRAINT assessment_revisions_actor_owner_fkey
        FOREIGN KEY (assessed_by_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION,
    CONSTRAINT assessment_revisions_identity_membership_key
        UNIQUE (recommendation_id,id,business_id,company_id),
    CONSTRAINT assessment_revisions_identity_business_key
        UNIQUE (recommendation_id,id,business_id),
    CONSTRAINT assessment_revisions_sequence_key
        UNIQUE (recommendation_id,revision_number)
);
CREATE INDEX IF NOT EXISTS assessment_revisions_business_company_assessed_idx
    ON operational.assessment_revisions (business_id,company_id,assessed_at DESC,id DESC);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='operational.recommendations'::regclass
          AND conname='recommendations_current_revision_membership_fkey'
    ) THEN
        ALTER TABLE operational.recommendations
            ADD CONSTRAINT recommendations_current_revision_membership_fkey
            FOREIGN KEY (id,current_revision_id,business_id,company_id)
            REFERENCES operational.assessment_revisions
                (recommendation_id,id,business_id,company_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS operational.offer_cycles (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL,
    company_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    selected_revision_id UUID NOT NULL,
    idempotency_key TEXT NOT NULL CHECK (idempotency_key<>''),
    payload_fingerprint TEXT NOT NULL CHECK (payload_fingerprint ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL CHECK (status IN ('preparing','sending','confirmed','abandoned','unknown')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    claim_token TEXT,
    lease_expires_at TIMESTAMPTZ,
    sending_started_at TIMESTAMPTZ,
    settled_at TIMESTAMPTZ,
    presented_at TIMESTAMPTZ,
    CONSTRAINT offer_cycles_recommendation_fkey
        FOREIGN KEY (recommendation_id,business_id,company_id)
        REFERENCES operational.recommendations(id,business_id,company_id) ON DELETE NO ACTION,
    CONSTRAINT offer_cycles_selected_revision_fkey
        FOREIGN KEY (recommendation_id,selected_revision_id,business_id,company_id)
        REFERENCES operational.assessment_revisions(recommendation_id,id,business_id,company_id)
        ON DELETE NO ACTION,
    CONSTRAINT offer_cycles_business_key UNIQUE (business_id,idempotency_key),
    CONSTRAINT offer_cycles_id_business_company_key UNIQUE (id,business_id,company_id),
    CHECK (
        (status='preparing' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL
            AND isfinite(lease_expires_at)
            AND lease_expires_at>created_at
            AND sending_started_at IS NULL AND settled_at IS NULL AND presented_at IS NULL)
        OR (status='sending' AND claim_token IS NOT NULL AND lease_expires_at IS NULL
            AND sending_started_at IS NOT NULL AND settled_at IS NULL AND presented_at IS NULL)
        OR (status='unknown' AND lease_expires_at IS NULL
            AND sending_started_at IS NOT NULL AND settled_at IS NOT NULL AND presented_at IS NULL)
        OR (status='confirmed' AND lease_expires_at IS NULL
            AND settled_at IS NOT NULL AND presented_at IS NOT NULL)
        OR (status='abandoned' AND lease_expires_at IS NULL
            AND settled_at IS NOT NULL AND presented_at IS NULL)
    ),
    CHECK (presented_at IS NULL OR presented_at<=settled_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS offer_cycles_one_pending_business_company_idx
    ON operational.offer_cycles (business_id,company_id)
    WHERE status IN ('preparing','sending','unknown');
CREATE INDEX IF NOT EXISTS offer_cycles_recommendation_history_idx
    ON operational.offer_cycles (business_id,recommendation_id,created_at DESC,id DESC);

CREATE TABLE IF NOT EXISTS operational.offer_cycle_events (
    id UUID PRIMARY KEY,
    offer_cycle_id UUID NOT NULL,
    business_id UUID NOT NULL,
    company_id UUID NOT NULL,
    event_kind TEXT NOT NULL CHECK (event_kind IN (
        'preparing_acquired','preparing_confirmed','preparing_abandoned',
        'preparing_expired','sending_authorized','sending_confirmed',
        'sending_failed','sending_unknown','unknown_resolved'
    )),
    actor_user_id UUID,
    reason TEXT,
    outcome TEXT CHECK (outcome IS NULL OR outcome IN ('confirmed','abandoned','pre_send_failed','unknown')),
    presented_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload)='object'),
    CONSTRAINT offer_cycle_events_cycle_fkey
        FOREIGN KEY (offer_cycle_id,business_id,company_id)
        REFERENCES operational.offer_cycles(id,business_id,company_id) ON DELETE NO ACTION,
    CONSTRAINT offer_cycle_events_actor_owner_fkey
        FOREIGN KEY (actor_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION,
    CHECK (event_kind<>'unknown_resolved' OR (
        actor_user_id IS NOT NULL AND reason IS NOT NULL AND btrim(reason)<>''
        AND outcome IS NOT NULL AND outcome IN ('confirmed','abandoned')
        AND resolved_at IS NOT NULL
        AND ((outcome='confirmed') = (presented_at IS NOT NULL))
    )),
    CHECK (presented_at IS NULL OR resolved_at IS NULL OR presented_at<=resolved_at)
);
CREATE INDEX IF NOT EXISTS offer_cycle_events_history_idx
    ON operational.offer_cycle_events (business_id,company_id,recorded_at,id);
CREATE UNIQUE INDEX IF NOT EXISTS offer_cycle_events_one_unknown_resolution_idx
    ON operational.offer_cycle_events (offer_cycle_id)
    WHERE event_kind='unknown_resolved';

CREATE TABLE IF NOT EXISTS operational.prospects (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL,
    company_id UUID NOT NULL REFERENCES gold.company(id) ON DELETE NO ACTION,
    stage TEXT NOT NULL CHECK (stage IN (
        'saved','contacted','in_conversation','proposal_sent','won_client','closed'
    )),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
    notes TEXT NOT NULL DEFAULT '',
    follow_up_at TIMESTAMPTZ,
    last_active_stage TEXT CHECK (last_active_stage IN (
        'saved','contacted','in_conversation','proposal_sent'
    )),
    CONSTRAINT prospects_business_fkey
        FOREIGN KEY (business_id) REFERENCES operational.businesses(id) ON DELETE NO ACTION,
    CONSTRAINT prospects_business_company_key UNIQUE (business_id,company_id),
    CONSTRAINT prospects_id_business_key UNIQUE (id,business_id),
    CONSTRAINT prospects_id_business_company_key UNIQUE (id,business_id,company_id),
    CHECK ((stage='closed') = (last_active_stage IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS prospects_business_stage_updated_idx
    ON operational.prospects (business_id,stage,updated_at DESC,id DESC);

CREATE TABLE IF NOT EXISTS operational.prospect_origins (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL,
    company_id UUID NOT NULL,
    prospect_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    assessment_revision_id UUID NOT NULL,
    created_by_user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT prospect_origins_prospect_fkey
        FOREIGN KEY (prospect_id,business_id,company_id)
        REFERENCES operational.prospects(id,business_id,company_id) ON DELETE NO ACTION,
    CONSTRAINT prospect_origins_recommendation_fkey
        FOREIGN KEY (recommendation_id,business_id,company_id)
        REFERENCES operational.recommendations(id,business_id,company_id) ON DELETE NO ACTION,
    CONSTRAINT prospect_origins_revision_fkey
        FOREIGN KEY (recommendation_id,assessment_revision_id,business_id,company_id)
        REFERENCES operational.assessment_revisions(recommendation_id,id,business_id,company_id)
        ON DELETE NO ACTION,
    CONSTRAINT prospect_origins_actor_owner_fkey
        FOREIGN KEY (created_by_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION,
    CONSTRAINT prospect_origins_exact_origin_key
        UNIQUE (business_id,recommendation_id,assessment_revision_id,prospect_id),
    CONSTRAINT prospect_origins_id_membership_key UNIQUE (id,business_id,prospect_id)
);
CREATE INDEX IF NOT EXISTS prospect_origins_prospect_created_idx
    ON operational.prospect_origins (business_id,prospect_id,created_at,id);

CREATE TABLE IF NOT EXISTS operational.prospect_activities (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL,
    prospect_id UUID NOT NULL,
    actor_user_id UUID NOT NULL,
    idempotency_key TEXT NOT NULL CHECK (idempotency_key<>''),
    payload_fingerprint TEXT NOT NULL CHECK (payload_fingerprint ~ '^[0-9a-f]{64}$'),
    kind TEXT NOT NULL CHECK (kind IN (
        'prospect_saved','stage_changed','closed','reopened','note_added',
        'follow_up_set','follow_up_cleared','proposal_drafted','proposal_sent','correction'
    )),
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload)='object'),
    origin_id UUID,
    correction_of_id UUID,
    CONSTRAINT prospect_activities_prospect_fkey
        FOREIGN KEY (prospect_id,business_id)
        REFERENCES operational.prospects(id,business_id) ON DELETE NO ACTION,
    CONSTRAINT prospect_activities_actor_owner_fkey
        FOREIGN KEY (actor_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION,
    CONSTRAINT prospect_activities_identity_membership_key
        UNIQUE (id,business_id,prospect_id),
    CONSTRAINT prospect_activities_request_key UNIQUE (business_id,idempotency_key),
    CONSTRAINT prospect_activities_origin_fkey
        FOREIGN KEY (origin_id,business_id,prospect_id)
        REFERENCES operational.prospect_origins(id,business_id,prospect_id) ON DELETE NO ACTION,
    CONSTRAINT prospect_activities_correction_fkey
        FOREIGN KEY (correction_of_id,business_id,prospect_id)
        REFERENCES operational.prospect_activities(id,business_id,prospect_id) ON DELETE NO ACTION,
    CHECK ((kind='correction') = (correction_of_id IS NOT NULL)),
    CHECK ((kind='prospect_saved') = (origin_id IS NOT NULL)),
    CHECK (correction_of_id IS NULL OR correction_of_id<>id),
    CHECK (kind<>'correction' OR payload ?& ARRAY['prior','replacement'])
);
CREATE INDEX IF NOT EXISTS prospect_activities_history_idx
    ON operational.prospect_activities (business_id,prospect_id,recorded_at,id);
CREATE UNIQUE INDEX IF NOT EXISTS prospect_activities_origin_once_idx
    ON operational.prospect_activities (origin_id) WHERE origin_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS operational.suppression_blocks (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL,
    company_id UUID NOT NULL REFERENCES gold.company(id) ON DELETE NO ACTION,
    kind TEXT NOT NULL CHECK (kind IN ('cooldown','pause','rejection')),
    created_at TIMESTAMPTZ NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    created_by_user_id UUID,
    expires_at TIMESTAMPTZ,
    cleared_at TIMESTAMPTZ,
    cleared_by_user_id UUID,
    reason TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
    CONSTRAINT suppression_blocks_business_fkey
        FOREIGN KEY (business_id) REFERENCES operational.businesses(id) ON DELETE NO ACTION,
    CONSTRAINT suppression_blocks_creator_owner_fkey
        FOREIGN KEY (created_by_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION,
    CONSTRAINT suppression_blocks_clearer_owner_fkey
        FOREIGN KEY (cleared_by_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION,
    CHECK (effective_at<=created_at),
    CHECK (expires_at IS NULL OR expires_at>effective_at),
    CHECK (kind<>'cooldown' OR expires_at IS NOT NULL),
    CHECK (kind<>'rejection' OR expires_at IS NULL),
    CHECK (kind NOT IN ('pause','rejection') OR created_by_user_id IS NOT NULL),
    CHECK ((cleared_at IS NULL) = (cleared_by_user_id IS NULL)),
    CHECK (cleared_at IS NULL OR cleared_at>=created_at)
);
CREATE INDEX IF NOT EXISTS suppression_blocks_active_projection_idx
    ON operational.suppression_blocks (business_id,company_id,kind,expires_at)
    WHERE cleared_at IS NULL;
CREATE INDEX IF NOT EXISTS suppression_blocks_history_idx
    ON operational.suppression_blocks (business_id,company_id,created_at,id);

CREATE TABLE IF NOT EXISTS operational.command_receipts (
    business_id UUID NOT NULL REFERENCES operational.businesses(id) ON DELETE NO ACTION,
    idempotency_key TEXT NOT NULL CHECK (idempotency_key<>''),
    scope TEXT NOT NULL CHECK (btrim(scope)<>''),
    payload_fingerprint TEXT NOT NULL CHECK (payload_fingerprint ~ '^[0-9a-f]{64}$'),
    resource_kind TEXT NOT NULL CHECK (btrim(resource_kind)<>''),
    resource_id UUID NOT NULL,
    resource_version INTEGER NOT NULL CHECK (resource_version>0),
    result_snapshot JSONB NOT NULL CHECK (jsonb_typeof(result_snapshot)='object'),
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (business_id,idempotency_key)
);

CREATE TABLE IF NOT EXISTS operational.recommendation_assessment_feedback (
    id UUID PRIMARY KEY,
    business_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    assessment_revision_id UUID NOT NULL,
    actor_user_id UUID NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload)='object'),
    CONSTRAINT recommendation_assessment_feedback_recommendation_fkey
        FOREIGN KEY (recommendation_id,business_id)
        REFERENCES operational.recommendations(id,business_id) ON DELETE NO ACTION,
    CONSTRAINT recommendation_assessment_feedback_revision_fkey
        FOREIGN KEY (recommendation_id,assessment_revision_id,business_id)
        REFERENCES operational.assessment_revisions(recommendation_id,id,business_id) ON DELETE NO ACTION,
    CONSTRAINT recommendation_assessment_feedback_actor_owner_fkey
        FOREIGN KEY (actor_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id) ON DELETE NO ACTION
);
CREATE INDEX IF NOT EXISTS recommendation_assessment_feedback_history_idx
    ON operational.recommendation_assessment_feedback
        (business_id,recommendation_id,assessment_revision_id,recorded_at,id);

CREATE OR REPLACE FUNCTION operational.reject_prospect_history_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'prospecting history is immutable' USING ERRCODE='55000';
END $$;

CREATE OR REPLACE FUNCTION operational.guard_recommendation_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    old_revision_number INTEGER;
    new_revision_number INTEGER;
BEGIN
    IF ROW(NEW.id,NEW.business_id,NEW.company_id,NEW.created_at)
       IS DISTINCT FROM ROW(OLD.id,OLD.business_id,OLD.company_id,OLD.created_at) THEN
        RAISE EXCEPTION 'recommendation identity is immutable' USING ERRCODE='55000';
    END IF;
    IF NEW.version<>OLD.version+1 OR NEW.updated_at<OLD.updated_at THEN
        RAISE EXCEPTION 'recommendation updates require a newer version and time' USING ERRCODE='23514';
    END IF;
    IF OLD.status<>'open' THEN
        IF OLD.first_presented_at IS NOT NULL OR NEW.first_presented_at IS NULL OR
           ROW(NEW.status,NEW.current_revision_id,NEW.resolved_at,
               NEW.resolved_by_user_id,NEW.resolution_reason)
           IS DISTINCT FROM ROW(OLD.status,OLD.current_revision_id,OLD.resolved_at,
               OLD.resolved_by_user_id,OLD.resolution_reason) OR NOT EXISTS (
               SELECT 1 FROM operational.offer_cycles AS cycle
               WHERE cycle.recommendation_id=OLD.id
                 AND cycle.business_id=OLD.business_id
                 AND cycle.company_id=OLD.company_id
                 AND cycle.status='confirmed'
                 AND cycle.presented_at=NEW.first_presented_at
           ) THEN
            RAISE EXCEPTION 'resolved recommendation permits only confirmed first exposure recording' USING ERRCODE='55000';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.status NOT IN ('open','converted','rejected') THEN
        RAISE EXCEPTION 'invalid recommendation status' USING ERRCODE='23514';
    END IF;
    IF OLD.first_presented_at IS NOT NULL AND NEW.first_presented_at IS DISTINCT FROM OLD.first_presented_at THEN
        RAISE EXCEPTION 'first presentation time is immutable' USING ERRCODE='55000';
    END IF;
    IF OLD.first_presented_at IS NULL AND NEW.first_presented_at IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM operational.offer_cycles AS cycle
        WHERE cycle.recommendation_id=OLD.id
          AND cycle.business_id=OLD.business_id
          AND cycle.company_id=OLD.company_id
          AND cycle.status='confirmed'
          AND cycle.presented_at=NEW.first_presented_at
    ) THEN
        RAISE EXCEPTION 'first presentation must match a confirmed offer cycle' USING ERRCODE='23514';
    END IF;
    IF NEW.current_revision_id IS DISTINCT FROM OLD.current_revision_id THEN
        IF OLD.current_revision_id IS NOT NULL AND NEW.current_revision_id IS NULL THEN
            RAISE EXCEPTION 'current revision cannot be cleared' USING ERRCODE='23514';
        END IF;
        SELECT revision_number INTO new_revision_number
        FROM operational.assessment_revisions
        WHERE id=NEW.current_revision_id AND recommendation_id=NEW.id;
        IF NEW.current_revision_id IS NOT NULL AND new_revision_number IS NULL THEN
            RAISE EXCEPTION 'current revision must belong to recommendation' USING ERRCODE='23503';
        END IF;
        IF OLD.current_revision_id IS NOT NULL THEN
            SELECT revision_number INTO old_revision_number
            FROM operational.assessment_revisions WHERE id=OLD.current_revision_id;
            IF new_revision_number<=old_revision_number THEN
                RAISE EXCEPTION 'current revision can only advance' USING ERRCODE='23514';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION operational.guard_prospect_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id,NEW.business_id,NEW.company_id,NEW.created_at)
       IS DISTINCT FROM ROW(OLD.id,OLD.business_id,OLD.company_id,OLD.created_at) THEN
        RAISE EXCEPTION 'prospect identity is immutable' USING ERRCODE='55000';
    END IF;
    IF NEW.version<>OLD.version+1 OR NEW.updated_at<OLD.updated_at THEN
        RAISE EXCEPTION 'prospect updates require a newer version and time' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION operational.validate_prospect_correction()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    original_recorded_at TIMESTAMPTZ;
BEGIN
    IF NEW.correction_of_id IS NOT NULL THEN
        SELECT recorded_at INTO original_recorded_at
        FROM operational.prospect_activities
        WHERE id=NEW.correction_of_id
          AND business_id=NEW.business_id AND prospect_id=NEW.prospect_id;
        IF NEW.recorded_at<original_recorded_at THEN
            RAISE EXCEPTION 'correction cannot predate the activity it corrects' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION operational.require_unknown_resolution_audit()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    cycle_id UUID;
    cycle_status TEXT;
    cycle_presented_at TIMESTAMPTZ;
    cycle_settled_at TIMESTAMPTZ;
    expected_outcome TEXT;
    event_count INTEGER;
BEGIN
    IF TG_TABLE_NAME='offer_cycles' THEN
        IF OLD.status='unknown' AND NEW.status IN ('confirmed','abandoned') THEN
            cycle_id := NEW.id;
            expected_outcome := NEW.status;
        ELSE
            RETURN NULL;
        END IF;
    ELSE
        IF NEW.event_kind<>'unknown_resolved' THEN
            RETURN NULL;
        END IF;
        cycle_id := NEW.offer_cycle_id;
        expected_outcome := NEW.outcome;
    END IF;
    SELECT status,presented_at,settled_at INTO cycle_status,cycle_presented_at,cycle_settled_at
    FROM operational.offer_cycles WHERE id=cycle_id;
    IF TG_TABLE_NAME='offer_cycle_events' THEN
        IF cycle_status IS DISTINCT FROM expected_outcome OR
           cycle_presented_at IS DISTINCT FROM NEW.presented_at OR
           cycle_settled_at IS DISTINCT FROM NEW.resolved_at THEN
            RAISE EXCEPTION 'unknown resolution event must match settled cycle' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
    END IF;
    SELECT count(*) INTO event_count
    FROM operational.offer_cycle_events event
    WHERE event.offer_cycle_id=cycle_id
      AND event.event_kind='unknown_resolved'
      AND event.outcome=expected_outcome
      AND event.resolved_at=cycle_settled_at
      AND event.actor_user_id IS NOT NULL
      AND btrim(event.reason)<>'';
    IF event_count=0 THEN
        RAISE EXCEPTION 'unknown offer resolution requires attributed audit event' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION operational.guard_offer_cycle_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id,NEW.business_id,NEW.company_id,NEW.recommendation_id,
           NEW.selected_revision_id,NEW.idempotency_key,NEW.payload_fingerprint,NEW.created_at)
       IS DISTINCT FROM ROW(OLD.id,OLD.business_id,OLD.company_id,OLD.recommendation_id,
           OLD.selected_revision_id,OLD.idempotency_key,OLD.payload_fingerprint,OLD.created_at) THEN
        RAISE EXCEPTION 'offer cycle identity and selection are immutable' USING ERRCODE='55000';
    END IF;
    IF (NEW.claim_token IS DISTINCT FROM OLD.claim_token AND NOT (
            OLD.claim_token IS NOT NULL AND NEW.claim_token IS NULL
            AND OLD.status='preparing' AND NEW.status IN ('confirmed','abandoned')
        )) OR
       (OLD.lease_expires_at IS NOT NULL AND
        NEW.lease_expires_at IS DISTINCT FROM OLD.lease_expires_at AND NOT (
            NEW.lease_expires_at IS NULL AND OLD.status='preparing'
            AND NEW.status IN ('sending','confirmed','abandoned')
        )) OR
       (OLD.sending_started_at IS NOT NULL AND
        NEW.sending_started_at IS DISTINCT FROM OLD.sending_started_at) OR
       (OLD.settled_at IS NOT NULL AND NEW.settled_at IS DISTINCT FROM OLD.settled_at
        AND NOT (OLD.status='unknown' AND NEW.status IN ('confirmed','abandoned')
            AND NEW.settled_at IS NOT NULL AND isfinite(NEW.settled_at)
            AND NEW.settled_at>=OLD.settled_at)) OR
       (OLD.presented_at IS NOT NULL AND NEW.presented_at IS DISTINCT FROM OLD.presented_at) THEN
        RAISE EXCEPTION 'offer cycle times and claim token cannot be rewritten' USING ERRCODE='55000';
    END IF;
    IF NEW.updated_at<OLD.updated_at OR NOT (
        (OLD.status='preparing' AND NEW.status IN ('preparing','sending','confirmed','abandoned'))
        OR (OLD.status='sending' AND NEW.status IN ('sending','confirmed','abandoned','unknown'))
        OR (OLD.status='unknown' AND NEW.status IN ('unknown','confirmed','abandoned'))
        OR (OLD.status IN ('confirmed','abandoned') AND NEW.status=OLD.status)
    ) THEN
        RAISE EXCEPTION 'invalid offer cycle transition' USING ERRCODE='23514';
    END IF;
    IF OLD.status='preparing' AND NEW.status IN ('confirmed','abandoned')
       AND NEW.sending_started_at IS NOT NULL THEN
        RAISE EXCEPTION 'preparing offer cannot record a send authorization' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION operational.require_preparing_offer_cycle()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status<>'preparing' THEN
        RAISE EXCEPTION 'offer cycles must begin in Preparing' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION operational.guard_suppression_block_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id,NEW.business_id,NEW.company_id,NEW.kind,NEW.created_at,
           NEW.effective_at,NEW.created_by_user_id,NEW.expires_at,NEW.reason)
       IS DISTINCT FROM ROW(OLD.id,OLD.business_id,OLD.company_id,OLD.kind,OLD.created_at,
           OLD.effective_at,OLD.created_by_user_id,OLD.expires_at,OLD.reason) THEN
        RAISE EXCEPTION 'suppression decision is immutable' USING ERRCODE='55000';
    END IF;
    IF OLD.cleared_at IS NOT NULL OR NEW.version<>OLD.version+1 OR
       NEW.cleared_at IS NULL OR NEW.cleared_at<OLD.created_at THEN
        RAISE EXCEPTION 'suppression block may be cleared once with a newer version' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS assessment_revisions_immutable ON operational.assessment_revisions;
CREATE TRIGGER assessment_revisions_immutable BEFORE UPDATE OR DELETE
    ON operational.assessment_revisions FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS prospect_origins_immutable ON operational.prospect_origins;
CREATE TRIGGER prospect_origins_immutable BEFORE UPDATE OR DELETE
    ON operational.prospect_origins FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS prospect_activities_immutable ON operational.prospect_activities;
CREATE TRIGGER prospect_activities_immutable BEFORE UPDATE OR DELETE
    ON operational.prospect_activities FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS prospect_activities_validate_correction ON operational.prospect_activities;
CREATE TRIGGER prospect_activities_validate_correction BEFORE INSERT
    ON operational.prospect_activities FOR EACH ROW
    EXECUTE FUNCTION operational.validate_prospect_correction();
DROP TRIGGER IF EXISTS offer_cycle_events_immutable ON operational.offer_cycle_events;
CREATE TRIGGER offer_cycle_events_immutable BEFORE UPDATE OR DELETE
    ON operational.offer_cycle_events FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS offer_cycles_require_unknown_audit ON operational.offer_cycles;
CREATE CONSTRAINT TRIGGER offer_cycles_require_unknown_audit
    AFTER UPDATE ON operational.offer_cycles DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION operational.require_unknown_resolution_audit();
DROP TRIGGER IF EXISTS offer_cycle_events_match_unknown_resolution ON operational.offer_cycle_events;
CREATE CONSTRAINT TRIGGER offer_cycle_events_match_unknown_resolution
    AFTER INSERT ON operational.offer_cycle_events DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION operational.require_unknown_resolution_audit();
DROP TRIGGER IF EXISTS command_receipts_immutable ON operational.command_receipts;
CREATE TRIGGER command_receipts_immutable BEFORE UPDATE OR DELETE
    ON operational.command_receipts FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS recommendation_assessment_feedback_immutable
    ON operational.recommendation_assessment_feedback;
CREATE TRIGGER recommendation_assessment_feedback_immutable BEFORE UPDATE OR DELETE
    ON operational.recommendation_assessment_feedback FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS recommendations_guard_update ON operational.recommendations;
CREATE TRIGGER recommendations_guard_update BEFORE UPDATE
    ON operational.recommendations FOR EACH ROW
    EXECUTE FUNCTION operational.guard_recommendation_update();
DROP TRIGGER IF EXISTS recommendations_no_delete ON operational.recommendations;
CREATE TRIGGER recommendations_no_delete BEFORE DELETE
    ON operational.recommendations FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS prospects_guard_update ON operational.prospects;
CREATE TRIGGER prospects_guard_update BEFORE UPDATE
    ON operational.prospects FOR EACH ROW
    EXECUTE FUNCTION operational.guard_prospect_update();
DROP TRIGGER IF EXISTS prospects_no_delete ON operational.prospects;
CREATE TRIGGER prospects_no_delete BEFORE DELETE
    ON operational.prospects FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS offer_cycles_guard_update ON operational.offer_cycles;
CREATE TRIGGER offer_cycles_guard_update BEFORE UPDATE
    ON operational.offer_cycles FOR EACH ROW
    EXECUTE FUNCTION operational.guard_offer_cycle_update();
DROP TRIGGER IF EXISTS offer_cycles_start_preparing ON operational.offer_cycles;
CREATE TRIGGER offer_cycles_start_preparing BEFORE INSERT
    ON operational.offer_cycles FOR EACH ROW
    EXECUTE FUNCTION operational.require_preparing_offer_cycle();
DROP TRIGGER IF EXISTS offer_cycles_no_delete ON operational.offer_cycles;
CREATE TRIGGER offer_cycles_no_delete BEFORE DELETE
    ON operational.offer_cycles FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS suppression_blocks_guard_update ON operational.suppression_blocks;
CREATE TRIGGER suppression_blocks_guard_update BEFORE UPDATE
    ON operational.suppression_blocks FOR EACH ROW
    EXECUTE FUNCTION operational.guard_suppression_block_update();
DROP TRIGGER IF EXISTS suppression_blocks_no_delete ON operational.suppression_blocks;
CREATE TRIGGER suppression_blocks_no_delete BEFORE DELETE
    ON operational.suppression_blocks FOR EACH ROW
    EXECUTE FUNCTION operational.reject_prospect_history_mutation();

COMMIT;
