# Database schema

Hand-written DDL, not a migration tool. No migration framework has been chosen yet (architecture document section 10, open item). Apply in order:

1. `00_extensions.sql`
2. `ops.sql` (pipeline-run metadata; no foreign keys in or out, so it can apply anywhere after the extension, listed here early)
3. `bronze.sql`
4. `silver.sql`
5. `gold.sql`
6. `operational.sql` (references `gold.company`)

```
psql "$HUGINN_DATABASE_URL" -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
```

These match `docs/entities.md` and the architecture document as of ADR-0002. Column-by-column Type 1/Type 2 classification beyond the three fields in `gold.company_history` is still open (Jira KAN-20); revise `gold.sql` and `src/huginn/gold/dimensional.py` together when that lands.

## Upgrading a database that already exists

The six files above are the fresh-install path. A schema change made after a database was created needs an `ALTER` file as well, or the change exists only for new installs and every existing deployment keeps the old shape. Apply the relevant `ALTER` files to an existing database, in any order, once each:

```
psql "$HUGINN_DATABASE_URL" -f db/schema/gold-company-stage.sql
```

| File | Change |
| --- | --- |
| `gold-company-stage.sql` | `gold.company.stage`, the source's own funding/development classification |
| `gold-company-status.sql` | `gold.company.company_status`, registry lifecycle as the source spells it |
| `gold-company-scale.sql` | `gold.company.company_scale` plus the four headcount bands its CHECK enforces |
| `silver-yc-status-team-size.sql` | `silver.yc_listings.company_status` / `team_size` and their `resolved_signals` counterparts |
| `gold-company-signal-source-stable-id.sql` | `gold.company_signal.source_stable_id` and the `UNIQUE (source, source_stable_id)` of ADR-0007 |
| `silver-yc-industries-location.sql` | `silver.yc_listings.industries` (TEXT[]) / `all_locations` and their `resolved_signals` counterparts |
| `gold-business-sector-array.sql` | `gold.company.business_sector` widens TEXT to TEXT[] in both `company` and `company_history` |
| `silver-yc-former-names.sql` | `silver.yc_listings.former_names` and its `resolved_signals` counterpart, captured for the KAN-4 matcher |
| `silver-yc-batch.sql` | `silver.yc_listings.batch` and its `resolved_signals` counterpart, the funded batch a company joined YC in |
| `gold-company-yc-batch.sql` | `gold.company.yc_batch`, superseded by `gold-company-notes.sql` |
| `gold-company-notes.sql` | `gold.company.notes` replaces `yc_batch`, rewriting existing values into source-prefixed form |

All eleven are idempotent: re-running one on a database it has already been applied to is a no-op. Covered by `tests/elt/gold/test_company_signal_migration.py` for the signal key, by `tests/elt/gold/test_business_sector_array_migration.py` for the array widening, by `tests/elt/silver/test_upsert_sql_shape.py` for the Silver upsert column/placeholder parity, and by the fresh-install rebuild in CI for the rest.

Three need a word of warning, because idempotent does not mean unconditional:

1. `gold-company-scale.sql` drops and recreates the `company_scale` CHECK. Re-running it after a future change to the band list validates existing values against the new list, so adding a band and backfilling it are two steps, and adding a band that existing rows violate fails loudly rather than silently dropping rows.
2. `gold-company-signal-source-stable-id.sql` refuses to run against a pre-ADR table that already has rows, because those rows have no `source_stable_id` and no correct value can be invented for one. `gold.company_signal` is a derived fact table, so the recovery is `TRUNCATE gold.company_signal` and a re-run of the Gold signal writer. It does not refuse a table that has the column, so re-running it after facts have accumulated is fine.
3. `gold-business-sector-array.sql` is guarded on the column's current type, not merely on its existence, and that guard is not optional. Re-applying `ARRAY[business_sector]` to a column that already holds `TEXT[]` wraps every value one dimension deeper, raising no error and leaving the column type at `text[]`. Its tests therefore assert `array_ndims` and the literal value, not just the type, because the type alone does not detect it.
