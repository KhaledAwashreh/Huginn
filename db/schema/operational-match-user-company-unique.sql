-- Enforce the durable User-Company Match identity for existing databases.
-- See openspec/changes/simple-matchmaking-service/design.md, Migration Plan.

BEGIN;

LOCK TABLE operational.match IN ACCESS EXCLUSIVE MODE;

DO $migration$
DECLARE
    target_table CONSTANT oid := 'operational.match'::regclass;
    target_schema CONSTANT oid := 'operational'::regnamespace;
    user_attnum CONSTANT smallint := (
        SELECT attnum FROM pg_attribute
        WHERE attrelid = 'operational.match'::regclass
          AND attname = 'user_id' AND NOT attisdropped
    );
    company_attnum CONSTANT smallint := (
        SELECT attnum FROM pg_attribute
        WHERE attrelid = 'operational.match'::regclass
          AND attname = 'company_id' AND NOT attisdropped
    );
    canonical_constraint record;
    canonical_relation record;
    equivalent_count integer;
    equivalent_name text;
    duplicate_pair_count bigint;
    duplicate_samples text;
    canonical_is_equivalent boolean;
BEGIN
    SELECT count(*) INTO duplicate_pair_count
    FROM (
        SELECT user_id, company_id
        FROM operational.match
        GROUP BY user_id, company_id
        HAVING count(*) > 1
    ) AS duplicate_pairs;

    IF duplicate_pair_count > 0 THEN
        SELECT string_agg(sample, E'\n' ORDER BY user_id, company_id)
        INTO duplicate_samples
        FROM (
            SELECT user_id, company_id,
                   format('user_id=%s company_id=%s match_ids=%s',
                          user_id, company_id,
                          array_agg(id ORDER BY id)) AS sample
            FROM operational.match
            GROUP BY user_id, company_id
            HAVING count(*) > 1
            ORDER BY user_id, company_id
            LIMIT 20
        ) AS duplicate_sample_rows;

        RAISE EXCEPTION
            'Cannot add operational.match_user_company_unique: % duplicate User-Company pair(s). Sample pairs (maximum 20): %',
            duplicate_pair_count, duplicate_samples
            USING ERRCODE = '23505';
    END IF;

    SELECT c.oid, c.conrelid, c.connamespace, c.contype, c.condeferrable,
           c.condeferred, c.convalidated, c.conkey, c.conindid,
           ni.nspname AS index_schema, ci.relname AS index_name,
           i.indrelid, i.indisunique, i.indisvalid, i.indisready, i.indislive,
           i.indimmediate, i.indnkeyatts, i.indnatts, i.indkey,
           i.indexprs, i.indpred, am.amname
    INTO canonical_constraint
    FROM pg_constraint AS c
    LEFT JOIN pg_class AS ci ON ci.oid = c.conindid
    LEFT JOIN pg_namespace AS ni ON ni.oid = ci.relnamespace
    LEFT JOIN pg_index AS i ON i.indexrelid = c.conindid
    LEFT JOIN pg_class AS ct ON ct.oid = i.indrelid
    LEFT JOIN pg_am AS am ON am.oid = ci.relam
    WHERE c.conrelid = target_table
      AND c.conname = 'match_user_company_unique';

    SELECT cl.oid, cl.relkind, cl.relname
    INTO canonical_relation
    FROM pg_class AS cl
    JOIN pg_namespace AS n ON n.oid = cl.relnamespace
    WHERE n.oid = target_schema
      AND cl.relname = 'match_user_company_unique';

    SELECT count(*), min(c.conname)
    INTO equivalent_count, equivalent_name
    FROM pg_constraint AS c
    JOIN pg_index AS i ON i.indexrelid = c.conindid
    JOIN pg_class AS ci ON ci.oid = i.indexrelid
    JOIN pg_namespace AS ni ON ni.oid = ci.relnamespace
    JOIN pg_class AS ct ON ct.oid = i.indrelid
    JOIN pg_am AS am ON am.oid = ci.relam
    WHERE c.conrelid = target_table
      AND c.connamespace = target_schema
      AND c.contype = 'u'
      AND NOT c.condeferrable
      AND NOT c.condeferred
      AND c.convalidated
      AND c.conkey = ARRAY[user_attnum, company_attnum]::smallint[]
      AND ni.oid = target_schema
      AND i.indrelid = target_table
      AND i.indisunique AND i.indisvalid AND i.indisready AND i.indislive
      AND i.indimmediate
      AND i.indnkeyatts = 2 AND i.indnatts = 2
      AND ARRAY(SELECT unnest(i.indkey::smallint[])) = ARRAY[user_attnum, company_attnum]::smallint[]
      AND i.indexprs IS NULL AND i.indpred IS NULL
      AND am.amname = 'btree';

    IF equivalent_count > 1 THEN
        RAISE EXCEPTION
            'operational.match has % equivalent User-Company unique constraints; reconcile them explicitly',
            equivalent_count;
    END IF;

    canonical_is_equivalent := false;
    IF canonical_constraint.oid IS NOT NULL THEN
        canonical_is_equivalent :=
            canonical_constraint.connamespace = target_schema
            AND canonical_constraint.contype = 'u'
            AND NOT canonical_constraint.condeferrable
            AND NOT canonical_constraint.condeferred
            AND canonical_constraint.convalidated
            AND canonical_constraint.conkey = ARRAY[user_attnum, company_attnum]::smallint[]
            AND canonical_constraint.index_schema = 'operational'
            AND canonical_constraint.index_name = 'match_user_company_unique'
            AND canonical_constraint.indrelid = target_table
            AND canonical_constraint.indisunique
            AND canonical_constraint.indisvalid
            AND canonical_constraint.indisready
            AND canonical_constraint.indislive
            AND canonical_constraint.indimmediate
            AND canonical_constraint.indnkeyatts = 2
            AND canonical_constraint.indnatts = 2
            AND ARRAY(SELECT unnest(canonical_constraint.indkey::smallint[])) = ARRAY[user_attnum, company_attnum]::smallint[]
            AND canonical_constraint.indexprs IS NULL
            AND canonical_constraint.indpred IS NULL
            AND canonical_constraint.amname = 'btree';

        IF NOT coalesce(canonical_is_equivalent, false) THEN
            RAISE EXCEPTION
                'operational.match has a conflicting match_user_company_unique constraint; reconcile it explicitly';
        END IF;

        IF canonical_relation.oid IS DISTINCT FROM canonical_constraint.conindid
           OR canonical_relation.relkind <> 'i' THEN
            RAISE EXCEPTION
                'operational.match_user_company_unique relation conflicts with its constraint backing index';
        END IF;

        RETURN;
    END IF;

    IF canonical_relation.oid IS NOT NULL THEN
        RAISE EXCEPTION
            'operational.match_user_company_unique is occupied by a relation that is not the canonical Match constraint';
    END IF;

    IF equivalent_count > 1 THEN
        RAISE EXCEPTION
            'operational.match has % equivalent User-Company unique constraints; reconcile them explicitly',
            equivalent_count;
    ELSIF equivalent_count = 1 THEN
        EXECUTE format(
            'ALTER TABLE operational.match RENAME CONSTRAINT %I TO match_user_company_unique',
            equivalent_name
        );
        RETURN;
    END IF;

    EXECUTE 'ALTER TABLE operational.match '
            'ADD CONSTRAINT match_user_company_unique UNIQUE (user_id, company_id)';
END;
$migration$;

COMMIT;
