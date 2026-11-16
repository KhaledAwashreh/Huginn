-- Explicit storage setup after operational-prospecting.sql. Never startup IO.
-- This file does not enable a sender; cutover must quiesce legacy writers first.
BEGIN;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='operational'
        AND table_name='weekly_digest_deliveries' AND column_name='batch_id') THEN
        IF EXISTS (SELECT 1 FROM operational.weekly_digest_deliveries) THEN
            RAISE EXCEPTION 'inspect and explicitly clear obsolete weekly deliveries before setup' USING ERRCODE='55000';
        END IF;
        ALTER TABLE operational.weekly_digest_deliveries
            DROP COLUMN batch_id, DROP COLUMN recipient, DROP COLUMN subject,
            DROP COLUMN body, DROP COLUMN company_ids;
    END IF;
END $$;

ALTER TABLE operational.weekly_digest_deliveries
    ADD COLUMN IF NOT EXISTS current_content_id UUID,
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1 CHECK (version>0),
    ADD COLUMN IF NOT EXISTS sending_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='operational.weekly_digest_deliveries'::regclass AND conname='weekly_digest_delivery_business_key') THEN
        ALTER TABLE operational.weekly_digest_deliveries ADD CONSTRAINT weekly_digest_delivery_business_key UNIQUE(id,business_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='operational.weekly_digest_deliveries'::regclass AND conname='weekly_digest_delivery_membership_key') THEN
        ALTER TABLE operational.weekly_digest_deliveries ADD CONSTRAINT weekly_digest_delivery_membership_key UNIQUE(id,business_id,recipient_user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='operational.offer_cycles'::regclass AND conname='offer_cycles_exact_selection_key') THEN
        ALTER TABLE operational.offer_cycles ADD CONSTRAINT offer_cycles_exact_selection_key UNIQUE(id,business_id,company_id,recommendation_id,selected_revision_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='operational.weekly_digest_deliveries'::regclass AND conname='weekly_digest_delivery_chronology_check') THEN
        ALTER TABLE operational.weekly_digest_deliveries ADD CONSTRAINT weekly_digest_delivery_chronology_check CHECK (
            isfinite(created_at)
            AND (sending_started_at IS NULL OR (isfinite(sending_started_at) AND sending_started_at>=created_at))
            AND (settled_at IS NULL OR (isfinite(settled_at) AND settled_at>=COALESCE(sending_started_at,created_at)))
            AND (accepted_at IS NULL OR (isfinite(accepted_at) AND accepted_at>=sending_started_at AND accepted_at<=settled_at))
            AND (
                (state='preparing' AND sending_started_at IS NULL AND settled_at IS NULL AND accepted_at IS NULL)
                OR (state='sending' AND current_content_id IS NOT NULL AND sending_started_at IS NOT NULL AND settled_at IS NULL AND accepted_at IS NULL)
                OR (state='sent' AND current_content_id IS NOT NULL AND sending_started_at IS NOT NULL AND settled_at IS NOT NULL AND accepted_at IS NOT NULL)
                OR (state='unknown' AND current_content_id IS NOT NULL AND sending_started_at IS NOT NULL AND settled_at IS NOT NULL AND accepted_at IS NULL)
                OR (state IN ('empty','suppressed') AND sending_started_at IS NULL AND settled_at IS NOT NULL AND accepted_at IS NULL)
                OR (state='failed' AND settled_at IS NOT NULL AND accepted_at IS NULL AND (sending_started_at IS NULL OR current_content_id IS NOT NULL))
            )
        );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS operational.weekly_digest_contents (
    id UUID PRIMARY KEY,
    delivery_id UUID NOT NULL,
    business_id UUID NOT NULL,
    recipient_user_id UUID NOT NULL,
    version INTEGER NOT NULL CHECK(version>0),
    created_at TIMESTAMPTZ NOT NULL CHECK(isfinite(created_at)),
    subscription_updated_at TIMESTAMPTZ NOT NULL CHECK(isfinite(subscription_updated_at)),
    recipient TEXT NOT NULL CHECK(btrim(recipient)<>'' AND recipient !~ '[[:cntrl:]]'),
    subject TEXT NOT NULL CHECK(btrim(subject)<>'' AND subject !~ '[[:cntrl:]]'),
    body TEXT NOT NULL CHECK(btrim(body)<>''),
    message_id TEXT NOT NULL CHECK(btrim(message_id)<>'' AND message_id !~ '[[:cntrl:]]'),
    created_in_xact XID8 NOT NULL DEFAULT pg_current_xact_id(),
    CONSTRAINT weekly_digest_contents_reservation_fkey
        FOREIGN KEY(delivery_id,business_id,recipient_user_id)
        REFERENCES operational.weekly_digest_deliveries(id,business_id,recipient_user_id),
    CONSTRAINT weekly_digest_contents_membership_key UNIQUE(id,delivery_id,business_id),
    CONSTRAINT weekly_digest_contents_version_key UNIQUE(delivery_id,version)
);

CREATE TABLE IF NOT EXISTS operational.weekly_digest_members (
    content_id UUID NOT NULL,
    delivery_id UUID NOT NULL,
    business_id UUID NOT NULL,
    company_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    assessment_revision_id UUID NOT NULL,
    offer_cycle_id UUID NOT NULL,
    position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 7),
    PRIMARY KEY(content_id,position),
    UNIQUE(content_id,company_id),
    UNIQUE(content_id,recommendation_id),
    UNIQUE(content_id,offer_cycle_id),
    CONSTRAINT weekly_digest_members_content_fkey
        FOREIGN KEY(content_id,delivery_id,business_id)
        REFERENCES operational.weekly_digest_contents(id,delivery_id,business_id),
    CONSTRAINT weekly_digest_members_revision_fkey
        FOREIGN KEY(recommendation_id,assessment_revision_id,business_id,company_id)
        REFERENCES operational.assessment_revisions(recommendation_id,id,business_id,company_id),
    CONSTRAINT weekly_digest_members_cycle_fkey
        FOREIGN KEY(offer_cycle_id,business_id,company_id,recommendation_id,assessment_revision_id)
        REFERENCES operational.offer_cycles(id,business_id,company_id,recommendation_id,selected_revision_id)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='operational.weekly_digest_deliveries'::regclass AND conname='weekly_digest_current_content_fkey') THEN
        ALTER TABLE operational.weekly_digest_deliveries ADD CONSTRAINT weekly_digest_current_content_fkey
            FOREIGN KEY(current_content_id,id,business_id)
            REFERENCES operational.weekly_digest_contents(id,delivery_id,business_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION operational.begin_weekly_digest_content()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM operational.weekly_digest_deliveries d
        WHERE d.id=NEW.delivery_id AND d.business_id=NEW.business_id
        AND d.recipient_user_id=NEW.recipient_user_id AND d.state='preparing'
        FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'content requires an owned preparing reservation' USING ERRCODE='23514';
    END IF;
    NEW.created_in_xact=pg_current_xact_id();
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION operational.require_new_weekly_digest_content()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM operational.weekly_digest_contents c
        WHERE c.id=NEW.content_id AND c.delivery_id=NEW.delivery_id
        AND c.business_id=NEW.business_id AND c.created_in_xact=pg_current_xact_id();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'committed email membership is immutable' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION operational.validate_weekly_digest_membership(selected_content_id UUID)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE member_count INTEGER; first_position INTEGER; last_position INTEGER;
BEGIN
    SELECT count(*),min(position),max(position)
        INTO member_count,first_position,last_position
        FROM operational.weekly_digest_members WHERE content_id=selected_content_id;
    IF member_count NOT BETWEEN 1 AND 7 OR first_position<>1 OR last_position<>member_count THEN
        RAISE EXCEPTION 'frozen email requires one to seven consecutive members' USING ERRCODE='23514';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION operational.require_complete_weekly_digest_content()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM operational.validate_weekly_digest_membership(NEW.id);
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION operational.require_complete_weekly_digest_member()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM operational.validate_weekly_digest_membership(NEW.content_id);
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS weekly_digest_contents_begin ON operational.weekly_digest_contents;
CREATE TRIGGER weekly_digest_contents_begin BEFORE INSERT ON operational.weekly_digest_contents
    FOR EACH ROW EXECUTE FUNCTION operational.begin_weekly_digest_content();
DROP TRIGGER IF EXISTS weekly_digest_contents_immutable ON operational.weekly_digest_contents;
CREATE TRIGGER weekly_digest_contents_immutable BEFORE UPDATE OR DELETE ON operational.weekly_digest_contents
    FOR EACH ROW EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS weekly_digest_members_new_content ON operational.weekly_digest_members;
CREATE TRIGGER weekly_digest_members_new_content BEFORE INSERT ON operational.weekly_digest_members
    FOR EACH ROW EXECUTE FUNCTION operational.require_new_weekly_digest_content();
DROP TRIGGER IF EXISTS weekly_digest_members_immutable ON operational.weekly_digest_members;
CREATE TRIGGER weekly_digest_members_immutable BEFORE UPDATE OR DELETE ON operational.weekly_digest_members
    FOR EACH ROW EXECUTE FUNCTION operational.reject_prospect_history_mutation();
DROP TRIGGER IF EXISTS weekly_digest_contents_complete ON operational.weekly_digest_contents;
CREATE CONSTRAINT TRIGGER weekly_digest_contents_complete AFTER INSERT ON operational.weekly_digest_contents
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION operational.require_complete_weekly_digest_content();
DROP TRIGGER IF EXISTS weekly_digest_members_complete ON operational.weekly_digest_members;
CREATE CONSTRAINT TRIGGER weekly_digest_members_complete AFTER INSERT ON operational.weekly_digest_members
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION operational.require_complete_weekly_digest_member();

CREATE OR REPLACE FUNCTION operational.guard_weekly_digest_delivery_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE old_content_version INTEGER; new_content_version INTEGER;
BEGIN
    IF ROW(NEW.id,NEW.business_id,NEW.recipient_user_id,NEW.week_start,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.id,OLD.business_id,OLD.recipient_user_id,OLD.week_start,OLD.created_at) THEN
        RAISE EXCEPTION 'weekly reservation identity is immutable' USING ERRCODE='55000';
    END IF;
    IF NEW.version<>OLD.version+1 THEN
        RAISE EXCEPTION 'weekly reservation update requires the next version' USING ERRCODE='23514';
    END IF;
    IF OLD.state IN ('sent','empty','failed','suppressed') OR NOT (
        (OLD.state='preparing' AND NEW.state IN ('preparing','sending','empty','failed','suppressed'))
        OR (OLD.state='sending' AND NEW.state IN ('sent','unknown','failed'))
        OR (OLD.state='unknown' AND NEW.state IN ('sent','failed'))
    ) THEN
        RAISE EXCEPTION 'invalid weekly delivery transition' USING ERRCODE='23514';
    END IF;
    IF NEW.current_content_id IS DISTINCT FROM OLD.current_content_id THEN
        IF OLD.state<>'preparing' OR NEW.state<>'preparing' OR NEW.current_content_id IS NULL THEN
            RAISE EXCEPTION 'frozen content can only be selected before sending' USING ERRCODE='23514';
        END IF;
        SELECT version INTO new_content_version FROM operational.weekly_digest_contents
            WHERE id=NEW.current_content_id AND delivery_id=OLD.id AND business_id=OLD.business_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'content is outside this weekly reservation' USING ERRCODE='23503';
        END IF;
        SELECT version INTO old_content_version FROM operational.weekly_digest_contents WHERE id=OLD.current_content_id;
        IF new_content_version<>COALESCE(old_content_version,0)+1 THEN
            RAISE EXCEPTION 'content selection requires the next frozen version' USING ERRCODE='23514';
        END IF;
    ELSIF OLD.state='preparing' AND NEW.state='preparing' THEN
        RAISE EXCEPTION 'reservation update must change content or lifecycle' USING ERRCODE='23514';
    END IF;
    IF (OLD.sending_started_at IS NOT NULL AND NEW.sending_started_at IS DISTINCT FROM OLD.sending_started_at)
        OR (OLD.accepted_at IS NOT NULL AND NEW.accepted_at IS DISTINCT FROM OLD.accepted_at)
        OR (OLD.settled_at IS NOT NULL AND NEW.settled_at IS DISTINCT FROM OLD.settled_at AND NOT (
            OLD.state='unknown' AND NEW.state IN ('sent','failed') AND NEW.settled_at>=OLD.settled_at
        )) THEN
        RAISE EXCEPTION 'recorded weekly delivery chronology cannot be rewritten' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS weekly_digest_delivery_guard ON operational.weekly_digest_deliveries;
CREATE TRIGGER weekly_digest_delivery_guard BEFORE UPDATE ON operational.weekly_digest_deliveries
    FOR EACH ROW EXECUTE FUNCTION operational.guard_weekly_digest_delivery_update();
DROP TRIGGER IF EXISTS weekly_digest_delivery_no_delete ON operational.weekly_digest_deliveries;
CREATE TRIGGER weekly_digest_delivery_no_delete BEFORE DELETE ON operational.weekly_digest_deliveries
    FOR EACH ROW EXECUTE FUNCTION operational.reject_prospect_history_mutation();

CREATE TABLE IF NOT EXISTS operational.weekly_digest_delivery_events (
    id UUID PRIMARY KEY,
    delivery_id UUID NOT NULL,
    business_id UUID NOT NULL,
    delivery_version INTEGER NOT NULL CHECK(delivery_version>0),
    event_kind TEXT NOT NULL CHECK(event_kind IN (
        'reserved','content_prepared','content_replaced','sending_authorized','sent',
        'unknown','preparation_failed','pre_send_failed','empty','suppressed','unknown_resolved'
    )),
    recorded_at TIMESTAMPTZ NOT NULL CHECK(isfinite(recorded_at)),
    content_id UUID,
    actor_user_id UUID,
    reason TEXT,
    outcome TEXT CHECK(outcome IS NULL OR outcome IN ('sent','failed')),
    accepted_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(payload)='object'),
    UNIQUE(delivery_id,delivery_version),
    CONSTRAINT weekly_digest_event_delivery_fkey FOREIGN KEY(delivery_id,business_id)
        REFERENCES operational.weekly_digest_deliveries(id,business_id),
    CONSTRAINT weekly_digest_event_content_fkey FOREIGN KEY(content_id,delivery_id,business_id)
        REFERENCES operational.weekly_digest_contents(id,delivery_id,business_id),
    CONSTRAINT weekly_digest_event_actor_fkey FOREIGN KEY(actor_user_id,business_id)
        REFERENCES operational.businesses(owner_user_id,id),
    CHECK(accepted_at IS NULL OR (isfinite(accepted_at) AND accepted_at<=recorded_at)),
    CHECK(event_kind NOT IN ('content_prepared','content_replaced','sending_authorized','sent','unknown','pre_send_failed','unknown_resolved') OR content_id IS NOT NULL),
    CHECK(event_kind='unknown_resolved' OR outcome IS NULL),
    CHECK(event_kind<>'unknown_resolved' OR (
        actor_user_id IS NOT NULL AND reason IS NOT NULL AND btrim(reason)<>'' AND outcome IS NOT NULL
    )),
    CHECK((event_kind='sent' OR (event_kind='unknown_resolved' AND outcome='sent')) = (accepted_at IS NOT NULL))
);

DROP TRIGGER IF EXISTS weekly_digest_delivery_events_immutable ON operational.weekly_digest_delivery_events;
CREATE TRIGGER weekly_digest_delivery_events_immutable BEFORE UPDATE OR DELETE ON operational.weekly_digest_delivery_events
    FOR EACH ROW EXECUTE FUNCTION operational.reject_prospect_history_mutation();

CREATE OR REPLACE FUNCTION operational.require_weekly_unknown_resolution_audit()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE selected_delivery UUID; selected_business UUID; selected_version INTEGER;
BEGIN
    IF TG_TABLE_NAME='weekly_digest_deliveries' THEN
        IF OLD.state<>'unknown' OR NEW.state NOT IN ('sent','failed') THEN
            RETURN NULL;
        END IF;
        selected_delivery=NEW.id;
        selected_business=NEW.business_id;
        selected_version=NEW.version;
    ELSE
        IF NEW.event_kind<>'unknown_resolved' THEN
            RETURN NULL;
        END IF;
        selected_delivery=NEW.delivery_id;
        selected_business=NEW.business_id;
        selected_version=NEW.delivery_version;
    END IF;
    PERFORM 1 FROM operational.weekly_digest_deliveries d
        JOIN operational.weekly_digest_delivery_events e
            ON e.delivery_id=d.id AND e.business_id=d.business_id AND e.delivery_version=d.version
        WHERE d.id=selected_delivery AND d.business_id=selected_business AND d.version=selected_version
            AND d.state IN ('sent','failed') AND e.event_kind='unknown_resolved' AND e.outcome=d.state
            AND e.content_id IS NOT DISTINCT FROM d.current_content_id
            AND e.recorded_at=d.settled_at AND e.accepted_at IS NOT DISTINCT FROM d.accepted_at;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown weekly recovery requires matching attributed history' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS weekly_digest_delivery_unknown_audit ON operational.weekly_digest_deliveries;
CREATE CONSTRAINT TRIGGER weekly_digest_delivery_unknown_audit AFTER UPDATE ON operational.weekly_digest_deliveries
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION operational.require_weekly_unknown_resolution_audit();
DROP TRIGGER IF EXISTS weekly_digest_event_unknown_audit ON operational.weekly_digest_delivery_events;
CREATE CONSTRAINT TRIGGER weekly_digest_event_unknown_audit AFTER INSERT ON operational.weekly_digest_delivery_events
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION operational.require_weekly_unknown_resolution_audit();

CREATE OR REPLACE FUNCTION operational.require_initial_weekly_reservation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.state<>'preparing' OR NEW.version<>1 OR NEW.current_content_id IS NOT NULL
        OR NEW.sending_started_at IS NOT NULL OR NEW.settled_at IS NOT NULL OR NEW.accepted_at IS NOT NULL THEN
        RAISE EXCEPTION 'weekly reservation must start preparing without exposure' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS weekly_digest_delivery_initial_state ON operational.weekly_digest_deliveries;
CREATE TRIGGER weekly_digest_delivery_initial_state BEFORE INSERT ON operational.weekly_digest_deliveries
    FOR EACH ROW EXECUTE FUNCTION operational.require_initial_weekly_reservation();

COMMIT;
