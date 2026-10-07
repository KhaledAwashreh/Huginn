-- Support the correlated inclusive signal-window lookup used by matchmaking.
-- See openspec/changes/simple-matchmaking-service/design.md, Migration Plan.

BEGIN;

LOCK TABLE gold.company_signal IN SHARE MODE;

DO $migration$
DECLARE
    target_table CONSTANT oid := 'gold.company_signal'::regclass;
    target_schema CONSTANT oid := 'gold'::regnamespace;
    company_attnum CONSTANT smallint := (
        SELECT attnum FROM pg_attribute
        WHERE attrelid = 'gold.company_signal'::regclass
          AND attname = 'company_id' AND NOT attisdropped
    );
    occurred_attnum CONSTANT smallint := (
        SELECT attnum FROM pg_attribute
        WHERE attrelid = 'gold.company_signal'::regclass
          AND attname = 'occurred_at' AND NOT attisdropped
    );
    named_relation record;
    matching_index record;
BEGIN
    SELECT cl.oid, cl.relkind
    INTO named_relation
    FROM pg_class AS cl
    JOIN pg_namespace AS n ON n.oid = cl.relnamespace
    WHERE n.oid = target_schema
      AND cl.relname = 'company_signal_company_occurred_at_idx';

    IF named_relation.oid IS NULL THEN
        EXECUTE 'CREATE INDEX company_signal_company_occurred_at_idx '
                'ON gold.company_signal (company_id, occurred_at)';
        RETURN;
    END IF;

    SELECT i.indrelid, i.indisunique, i.indisvalid, i.indisready,
           i.indislive, i.indnkeyatts, i.indnatts, i.indkey,
           i.indclass, i.indcollation, i.indoption, i.indexprs,
           i.indpred, am.amname,
           EXISTS (
               SELECT 1 FROM pg_constraint AS c WHERE c.conindid = i.indexrelid
           ) AS owned_by_constraint
    INTO matching_index
    FROM pg_index AS i
    JOIN pg_class AS index_class ON index_class.oid = i.indexrelid
    JOIN pg_am AS am ON am.oid = index_class.relam
    WHERE i.indexrelid = named_relation.oid;

    IF named_relation.relkind <> 'i'
       OR matching_index.indrelid IS DISTINCT FROM target_table
       OR matching_index.indisunique
       OR NOT matching_index.indisvalid
       OR NOT matching_index.indisready
       OR NOT matching_index.indislive
       OR matching_index.indnkeyatts <> 2
       OR matching_index.indnatts <> 2
       OR ARRAY(SELECT unnest(matching_index.indkey::smallint[])) <> ARRAY[company_attnum, occurred_attnum]::smallint[]
       OR matching_index.indexprs IS NOT NULL
       OR matching_index.indpred IS NOT NULL
       OR matching_index.amname <> 'btree'
       OR matching_index.owned_by_constraint
       OR ARRAY(SELECT unnest(matching_index.indoption::smallint[])) <> ARRAY[0, 0]::smallint[]
       OR ARRAY(SELECT unnest(matching_index.indcollation::oid[])) <> ARRAY[0, 0]::oid[]
       OR EXISTS (
           SELECT 1
           FROM unnest(matching_index.indclass::oid[]) AS opclass_oid
           JOIN pg_opclass AS opc ON opc.oid = opclass_oid
           WHERE NOT opc.opcdefault
       ) THEN
        RAISE EXCEPTION
            'gold.company_signal_company_occurred_at_idx exists with an incompatible definition; reconcile it explicitly';
    END IF;
END;
$migration$;

COMMIT;
