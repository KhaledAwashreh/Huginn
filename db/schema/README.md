# Database schema

These files are a fresh-database bootstrap, not migrations and not an
existing-data upgrade path. No migration framework has been chosen. Apply all
six files to a new database in this order:

1. `00_extensions.sql`
2. `ops.sql` (pipeline-run metadata; no foreign keys in or out, so it can apply anywhere after the extension, listed here early)
3. `bronze.sql`
4. `silver.sql`
5. `gold.sql`
6. `operational.sql` (references `gold.company`)

```bash
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
```

`ON_ERROR_STOP` and the single transaction make any SQL error fail the bootstrap without committing a partial schema. The management development database still receives every ELT schema because retained operational tables reference `gold.company`. Use a new, dedicated, disposable database; this bootstrap does not authorize dropping or resetting an existing database.

These match `docs/entities.md`, the [management foundation](../../docs/management-foundation.md), and the architecture document as of ADR-0002 and ADR-0011. Column-by-column Type 1/Type 2 classification beyond the two fields in `gold.company_history` is still open (Jira KAN-20); revise `gold.sql` and `src/huginn/elt/gold/dimensional.py` together when that lands.

## Upgrading a database that already exists

The six files above are the fresh-install path. A schema change made after a database was created needs an `ALTER` file as well, or the change exists only for new installs and every existing deployment keeps the old shape. Apply the relevant `ALTER` files to an existing database, once each. Order among them does not matter: each is idempotent and guards on the state it finds. The superseded pair is the one case worth knowing about, because it is why that holds: `gold-company-yc-batch.sql` can add `yc_batch` and `gold-company-notes.sql` is what removes it, so whichever of the two runs last decides the outcome unless the successor creates `notes` unconditionally, which it does. The pair converges on `notes` in either order:

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
| `gold-drop-icp-filter-pass.sql` | drops `icp_filter_pass` from `gold.company` and `gold.company_history`, per ADR-0012 |
| `gold-rename-company-type-to-legal-form.sql` | `gold.company.company_type` renamed to `legal_form`, the axis the column actually holds |
| `gold-eu-startups-searched-at.sql` | `gold.company.eu_startups_searched_at`, the EU-Startups search cursor, per ADR-0010 |

All fourteen are idempotent: re-running one on a database it has already been applied to is a no-op. Automated coverage of that claim is much thinner than the sentence implies:

1. Three of the fourteen are executed against a real Postgres by a test: `gold-company-signal-source-stable-id.sql` by `tests/elt/gold/test_company_signal_migration.py`, `gold-business-sector-array.sql` by `tests/elt/gold/test_business_sector_array_migration.py`, and `gold-eu-startups-searched-at.sql` by `tests/elt/gold/test_eu_startups_searched_at_migration.py`.
2. The other eleven have no idempotency or upgrade-path test at all. Nothing in the suite can detect a reordering regression among them.
3. The fresh-install rebuild in CI is not a substitute for the missing eleven. `tests/postgres_harness.py` applies the six base files listed above and none of the fourteen `ALTER` files, reached through the `integration_database_url` fixture, so it exercises `gold.sql` and `silver.sql` as shipped and never an `ALTER` script.
4. `tests/elt/silver/test_upsert_sql_shape.py` is a different kind of check: it asserts the Silver upsert's column and placeholder parity as text and applies no schema file.

Three need a word of warning, because idempotent does not mean unconditional:

1. `gold-company-scale.sql` drops and recreates the `company_scale` CHECK. Re-running it after a future change to the band list validates existing values against the new list, so adding a band and backfilling it are two steps, and adding a band that existing rows violate fails loudly rather than silently dropping rows.
2. `gold-company-signal-source-stable-id.sql` refuses to run against a pre-ADR table that already has rows, because those rows have no `source_stable_id` and no correct value can be invented for one. `gold.company_signal` is a derived fact table, so the recovery is `TRUNCATE gold.company_signal` and a re-run of the Gold signal writer. It does not refuse a table that has the column, so re-running it after facts have accumulated is fine.
3. `gold-business-sector-array.sql` is guarded on the column's current type, not merely on its existence, and that guard is not optional. Re-applying `ARRAY[business_sector]` to a column that already holds `TEXT[]` wraps every value one dimension deeper, raising no error and leaving the column type at `text[]`. Its tests therefore assert `array_ndims` and the literal value, not just the type, because the type alone does not detect it.
