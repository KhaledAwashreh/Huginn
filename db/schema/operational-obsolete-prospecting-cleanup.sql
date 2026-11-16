-- Explicit one-time obsolete-workflow cleanup. Never run at startup or from GET.
-- Disable admission and stop old workers before applying this transaction.
-- See docs/recommendation-prospect-cutover.md for target inspection and ordering.
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    table_name TEXT;
    relation REGCLASS;
    row_count BIGINT;
    trigger_row RECORD;
    trigger_mode "char";
    new_tables TEXT[] := ARRAY[
        'assessment_revisions', 'command_receipts', 'offer_cycle_events',
        'offer_cycles', 'prospect_activities', 'prospect_origins', 'prospects',
        'recommendation_assessment_feedback', 'recommendations', 'suppression_blocks',
        'weekly_digest_contents', 'weekly_digest_delivery_events', 'weekly_digest_members'
    ];
    legacy_tables TEXT[] := ARRAY[
        'communication_turn', 'communication_revision', 'communication_version',
        'communication', 'activity', 'match_feedback', 'match_score',
        'match_source_evidence', 'match', 'weekly_digest_deliveries',
        'recommendation_feedback', 'recommendation_batches'
    ];
BEGIN
    -- A consistent lock order also fences a concurrently submitted cleanup.
    FOR table_name IN
        SELECT DISTINCT item FROM unnest(new_tables || legacy_tables) AS names(item)
        ORDER BY item
    LOOP
        relation := to_regclass(format('operational.%I', table_name));
        IF relation IS NOT NULL THEN
            EXECUTE format('LOCK TABLE %s IN ACCESS EXCLUSIVE MODE', relation);
        END IF;
    END LOOP;

    IF to_regclass('ops.pipeline_execution_guard') IS NOT NULL THEN
        LOCK TABLE ops.pipeline_execution_guard IN SHARE MODE;
        IF EXISTS (SELECT 1 FROM ops.pipeline_execution_guard WHERE active) THEN
            RAISE EXCEPTION 'execution guard is active; quiesce workers first'
                USING ERRCODE = '55000';
        END IF;
    END IF;
    IF to_regclass('ops.matchmaking_runs') IS NOT NULL THEN
        LOCK TABLE ops.matchmaking_runs IN SHARE MODE;
        IF EXISTS (SELECT 1 FROM ops.matchmaking_runs WHERE state IN ('queued','running')) THEN
            RAISE EXCEPTION 'legacy matchmaking work is active; quiesce workers first'
                USING ERRCODE = '55000';
        END IF;
    END IF;
    IF to_regclass('ops.matchmaking_run_users') IS NOT NULL THEN
        LOCK TABLE ops.matchmaking_run_users IN SHARE MODE;
        IF EXISTS (SELECT 1 FROM ops.matchmaking_run_users WHERE state IN ('pending','running')) THEN
            RAISE EXCEPTION 'legacy matchmaking targets are active; quiesce workers first'
                USING ERRCODE = '55000';
        END IF;
    END IF;

    FOREACH table_name IN ARRAY new_tables LOOP
        relation := to_regclass(format('operational.%I', table_name));
        IF relation IS NOT NULL THEN
            EXECUTE format('SELECT count(*) FROM %s', relation) INTO row_count;
            IF row_count > 0 THEN
                RAISE EXCEPTION 'new workflow history exists in %; cleanup cannot be replayed', table_name
                    USING ERRCODE = '55000';
            END IF;
        END IF;
    END LOOP;

    IF to_regclass('operational.weekly_digest_deliveries') IS NOT NULL THEN
        SELECT count(*) INTO row_count FROM operational.weekly_digest_deliveries;
        IF row_count > 0 AND EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid='operational.weekly_digest_deliveries'::regclass
              AND attname='current_content_id' AND NOT attisdropped
        ) THEN
            RAISE EXCEPTION 'new workflow history exists in weekly_digest_deliveries; cleanup cannot be replayed'
                USING ERRCODE = '55000';
        END IF;
        IF EXISTS (SELECT 1 FROM operational.weekly_digest_deliveries WHERE state IN ('sending','unknown')) THEN
            RAISE EXCEPTION 'legacy delivery outcome is unresolved; explicit resolution is required'
                USING ERRCODE = '55000';
        END IF;
    END IF;

    -- Require the expected immutable guards. Do not silently change disabled,
    -- replica-only or ALWAYS trigger modes on an unexpected target schema.
    FOR trigger_row IN SELECT * FROM (VALUES
        ('match_source_evidence','match_source_evidence_immutable'),
        ('recommendation_feedback','recommendation_feedback_immutable'),
        ('recommendation_batches','recommendation_batches_immutable')
    ) AS guards(table_name, trigger_name) LOOP
        relation := to_regclass(format('operational.%I', trigger_row.table_name));
        IF relation IS NOT NULL THEN
            SELECT tgenabled INTO trigger_mode FROM pg_trigger
            WHERE tgrelid=relation AND tgname=trigger_row.trigger_name AND NOT tgisinternal;
            IF trigger_mode IS DISTINCT FROM 'O'::"char" THEN
                RAISE EXCEPTION 'unexpected immutable guard on %', trigger_row.table_name
                    USING ERRCODE = '55000';
            END IF;
            EXECUTE format('ALTER TABLE %s DISABLE TRIGGER %I', relation, trigger_row.trigger_name);
        END IF;
    END LOOP;

    -- Enumerated FK order; unexpected dependent tables fail and roll back the
    -- entire transaction, including earlier deletes and trigger changes.
    FOREACH table_name IN ARRAY legacy_tables LOOP
        relation := to_regclass(format('operational.%I', table_name));
        IF relation IS NOT NULL THEN
            EXECUTE format('DELETE FROM %s', relation);
            GET DIAGNOSTICS row_count = ROW_COUNT;
            RAISE NOTICE 'obsolete workflow %: removed % rows', table_name, row_count;
        END IF;
    END LOOP;

    FOR trigger_row IN SELECT * FROM (VALUES
        ('match_source_evidence','match_source_evidence_immutable'),
        ('recommendation_feedback','recommendation_feedback_immutable'),
        ('recommendation_batches','recommendation_batches_immutable')
    ) AS guards(table_name, trigger_name) LOOP
        relation := to_regclass(format('operational.%I', trigger_row.table_name));
        IF relation IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %s ENABLE TRIGGER %I', relation, trigger_row.trigger_name);
        END IF;
    END LOOP;
END $$;
COMMIT;
