-- Guarded current source context and append-only Match evidence.
-- See docs/source-currentness.md.
BEGIN;
SET LOCAL search_path = pg_catalog, public;

CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS operational;

-- Preserved context is history. Existing disposable tests must leave it in
-- place until their provisioned database is torn down.
CREATE OR REPLACE FUNCTION silver.reject_source_context_snapshot_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'source context snapshots are immutable'
        USING ERRCODE = '55000';
END $$;
DROP TRIGGER IF EXISTS source_context_snapshot_immutable
    ON silver.source_context_snapshot;
CREATE TRIGGER source_context_snapshot_immutable
    BEFORE UPDATE OR DELETE ON silver.source_context_snapshot
    FOR EACH ROW EXECUTE FUNCTION silver.reject_source_context_snapshot_mutation();

CREATE OR REPLACE VIEW gold.current_source_evidence AS
WITH bronze_current AS (
    SELECT source, stable_id, payload, fetched_at
    FROM bronze.api_ingest WHERE source IN ('hn', 'yc')
    UNION ALL
    SELECT source, stable_id, payload, fetched_at
    FROM bronze.web_scrape_ingest WHERE source = 'eu_startups'
),
expected_versions(source, policy_version, parser_version) AS (
    VALUES
        ('hn', 'source-lifecycle-v2', 'hn-context-v1'),
        ('yc', 'source-lifecycle-v2', 'yc-context-v1'),
        ('eu_startups', 'source-lifecycle-v2', 'eu-startups-context-v1')
)
SELECT
    gs.id,
    gs.company_id,
    o.id AS observation_id,
    CASE WHEN o.source = 'hn' OR (o.source = 'yc' AND o.hiring_state = 'true')
         THEN 'hiring' ELSE 'other' END AS signal_type,
    o.source,
    o.stable_id AS source_stable_id,
    s.source_url,
    s.normalized_text AS description,
    s.source_fields ->> 'stage' AS stage,
    o.occurred_at,
    gs.ingested_at,
    o.observed_at,
    CASE WHEN o.source = 'hn' OR (o.source = 'yc' AND o.hiring_state = 'true')
         THEN 'hiring' ELSE 'directory_context' END AS evidence_kind,
    o.hiring_state,
    CASE WHEN o.source = 'eu_startups' AND jsonb_typeof(s.source_fields->'category') = 'string'
         THEN s.source_fields->>'category' END AS source_country
FROM silver.source_currentness AS current
JOIN silver.source_lifecycle_observation AS o
  ON o.source = current.source
 AND o.stable_id = current.stable_id
 AND o.id = current.current_observation_id
JOIN expected_versions AS version ON version.source = o.source
JOIN bronze_current AS b ON b.source = o.source AND b.stable_id = o.stable_id
JOIN silver.resolved_signals AS r
  ON r.source = o.source AND r.source_stable_id = o.stable_id
JOIN gold.company AS c ON c.id = o.company_id
JOIN silver.source_context_snapshot AS s
  ON s.id = o.snapshot_id
 AND s.source = o.source
 AND s.stable_id = o.stable_id
 AND s.parser_version = version.parser_version
JOIN gold.company_signal AS gs
  ON gs.source = o.source
 AND gs.source_stable_id = o.stable_id
 AND gs.company_id = o.company_id
WHERE o.listing_state = 'available'
  AND o.identity_state = 'consistent'
  AND o.company_id IS NOT NULL
  AND o.policy_version = version.policy_version
  AND o.context_version = version.parser_version
  AND o.raw_token = md5(b.payload::text)
  AND o.resolution_token = md5(jsonb_build_array(
      r.resolved_company_key, r.key_derivation)::text)
  AND o.key_derivation = 'domain_normalized'
  AND r.key_derivation = 'domain_normalized'
  AND o.resolved_company_key = r.resolved_company_key
  AND o.explicit_domain = o.resolved_company_key
  AND c.domain = o.resolved_company_key
  AND c.domain = o.explicit_domain;

CREATE TABLE IF NOT EXISTS operational.match_source_evidence (
    match_id UUID NOT NULL,
    observation_id UUID NOT NULL,
    cutoff TIMESTAMPTZ NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    CONSTRAINT match_source_evidence_pkey PRIMARY KEY (match_id, observation_id),
    CONSTRAINT match_source_evidence_window_ck CHECK (cutoff <= as_of),
    CONSTRAINT match_source_evidence_match_fkey FOREIGN KEY (match_id)
        REFERENCES operational.match (id),
    CONSTRAINT match_source_evidence_observation_fkey FOREIGN KEY (observation_id)
        REFERENCES silver.source_lifecycle_observation (id)
);

CREATE TEMP TABLE _match_source_evidence_expected (
    match_id UUID NOT NULL,
    observation_id UUID NOT NULL,
    cutoff TIMESTAMPTZ NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    CONSTRAINT match_source_evidence_pkey PRIMARY KEY (match_id, observation_id),
    CONSTRAINT match_source_evidence_window_ck CHECK (cutoff <= as_of)
) ON COMMIT DROP;

DO $$
DECLARE
    actual_columns JSONB;
    expected_columns JSONB;
    actual_constraints TEXT[];
    expected_constraints TEXT[];
BEGIN
    SELECT jsonb_agg(jsonb_build_array(a.attname, a.atttypid, a.atttypmod,
                a.attnotnull, pg_get_expr(d.adbin, d.adrelid)) ORDER BY a.attnum)
    INTO expected_columns
    FROM pg_attribute a LEFT JOIN pg_attrdef d
      ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE a.attrelid = 'pg_temp._match_source_evidence_expected'::regclass
      AND a.attnum > 0 AND NOT a.attisdropped;
    SELECT jsonb_agg(jsonb_build_array(a.attname, a.atttypid, a.atttypmod,
                a.attnotnull, pg_get_expr(d.adbin, d.adrelid)) ORDER BY a.attnum)
    INTO actual_columns
    FROM pg_attribute a LEFT JOIN pg_attrdef d
      ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE a.attrelid = 'operational.match_source_evidence'::regclass
      AND a.attnum > 0 AND NOT a.attisdropped;
    IF actual_columns IS DISTINCT FROM expected_columns THEN
        RAISE EXCEPTION 'incompatible match source evidence columns';
    END IF;
    SELECT array_agg(contype::text || ':' || pg_get_constraintdef(oid)
                     ORDER BY contype::text || ':' || pg_get_constraintdef(oid))
    INTO expected_constraints FROM pg_constraint
    WHERE conrelid = 'pg_temp._match_source_evidence_expected'::regclass;
    SELECT array_agg(contype::text || ':' || pg_get_constraintdef(oid)
                     ORDER BY contype::text || ':' || pg_get_constraintdef(oid))
    INTO actual_constraints FROM pg_constraint
    WHERE conrelid = 'operational.match_source_evidence'::regclass
      AND contype <> 'f';
    IF actual_constraints IS DISTINCT FROM expected_constraints THEN
        RAISE EXCEPTION 'incompatible match source evidence constraints';
    END IF;
    IF (SELECT count(*) FROM pg_constraint
        WHERE conrelid = 'operational.match_source_evidence'::regclass
          AND contype = 'f') <> 2
       OR NOT EXISTS (
           SELECT 1 FROM pg_constraint fk
           WHERE fk.conrelid = 'operational.match_source_evidence'::regclass
             AND fk.contype = 'f'
             AND fk.confrelid = 'operational.match'::regclass
             AND fk.conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                    WHERE attrelid = fk.conrelid
                                      AND attname = 'match_id')]
             AND fk.confkey = ARRAY[(SELECT attnum FROM pg_attribute
                                     WHERE attrelid = fk.confrelid
                                       AND attname = 'id')]
             AND fk.confdeltype = 'a' AND fk.confupdtype = 'a'
             AND fk.convalidated AND NOT fk.condeferrable AND NOT fk.condeferred
       )
       OR NOT EXISTS (
           SELECT 1 FROM pg_constraint fk
           WHERE fk.conrelid = 'operational.match_source_evidence'::regclass
             AND fk.contype = 'f'
             AND fk.confrelid = 'silver.source_lifecycle_observation'::regclass
             AND fk.conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                    WHERE attrelid = fk.conrelid
                                      AND attname = 'observation_id')]
             AND fk.confkey = ARRAY[(SELECT attnum FROM pg_attribute
                                     WHERE attrelid = fk.confrelid
                                       AND attname = 'id')]
             AND fk.confdeltype = 'a' AND fk.confupdtype = 'a'
             AND fk.convalidated AND NOT fk.condeferrable AND NOT fk.condeferred
       ) THEN
        RAISE EXCEPTION 'incompatible match source evidence foreign keys';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS match_source_evidence_observation_idx
    ON operational.match_source_evidence (observation_id);

CREATE OR REPLACE FUNCTION operational.validate_match_source_evidence()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM operational.match AS m
        JOIN gold.current_source_evidence AS evidence
          ON evidence.observation_id = NEW.observation_id
         AND evidence.company_id = m.company_id
        WHERE m.id = NEW.match_id
          AND evidence.occurred_at IS NOT NULL
          AND evidence.occurred_at >= NEW.cutoff
          AND evidence.occurred_at <= NEW.as_of
    ) THEN
        RAISE EXCEPTION 'Match evidence is not current, company-consistent, or within the requested window'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS match_source_evidence_validate
    ON operational.match_source_evidence;
CREATE TRIGGER match_source_evidence_validate
    BEFORE INSERT ON operational.match_source_evidence
    FOR EACH ROW EXECUTE FUNCTION operational.validate_match_source_evidence();

CREATE OR REPLACE FUNCTION operational.reject_match_source_evidence_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Match source evidence is immutable'
        USING ERRCODE = '55000';
END $$;
DROP TRIGGER IF EXISTS match_source_evidence_immutable
    ON operational.match_source_evidence;
CREATE TRIGGER match_source_evidence_immutable
    BEFORE UPDATE OR DELETE ON operational.match_source_evidence
    FOR EACH ROW EXECUTE FUNCTION operational.reject_match_source_evidence_mutation();

CREATE OR REPLACE FUNCTION operational.preserve_match_evidence_identity()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.id IS DISTINCT FROM NEW.id
       OR OLD.user_id IS DISTINCT FROM NEW.user_id
       OR OLD.company_id IS DISTINCT FROM NEW.company_id THEN
        RAISE EXCEPTION 'Match identity is immutable'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS match_evidence_identity_immutable ON operational.match;
CREATE TRIGGER match_evidence_identity_immutable
    BEFORE UPDATE ON operational.match
    FOR EACH ROW EXECUTE FUNCTION operational.preserve_match_evidence_identity();

COMMIT;
