# Database schema

These files are a fresh-database bootstrap, not migrations. No migration
framework has been chosen. Apply all seven files to a new database in this
order:

1. `00_extensions.sql`
2. `ops.sql` (pipeline-run metadata; no foreign keys in or out, so it can apply anywhere after the extension, listed here early)
3. `bronze.sql`
4. `kan-83-eu-startups-discovery.sql`
5. `silver.sql`
6. `gold.sql`
7. `operational.sql` (references `gold.company`)

```bash
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f db/schema/00_extensions.sql -f db/schema/ops.sql -f db/schema/bronze.sql -f db/schema/kan-83-eu-startups-discovery.sql -f db/schema/silver.sql -f db/schema/gold.sql -f db/schema/operational.sql
```

`ON_ERROR_STOP` and the single transaction make any SQL error fail the bootstrap without committing a partial schema. The management development database still receives every ELT schema because retained operational tables reference `gold.company`. Use a new, dedicated, disposable database; this bootstrap does not authorize dropping or resetting an existing database.

## Existing Pre-KAN-83 Databases

The KAN-83 rollout has three idempotent additive upgrades for a database with
the prior Bronze and Silver schemas. Together they add EU-Startups discovery
state and retry tables, supporting indexes, the per-source Silver staging
table, and its tracking fields; they do not alter or remove existing data:

```bash
rtk proxy psql "$HUGINN_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f db/schema/kan-83-eu-startups-discovery.sql -f db/schema/silver-eu-startups-listings.sql -f db/schema/silver-eu-startups-tracking-fields.sql
```

For discovery-only use on a pre-KAN-83 database, apply
`kan-83-eu-startups-discovery.sql` before invoking
`python -m huginn.elt.ingestion eu-startups-discovery`. Silver staging and
materialization also require `silver-eu-startups-listings.sql` followed by
`silver-eu-startups-tracking-fields.sql`. The full `python -m huginn.elt`
pipeline uses discovery, the three EU rollout upgrades, shared resolution, and
Gold; apply those EU upgrades plus any other applicable Silver and Gold
upgrades below for schema changes the pipeline uses. EU enrichment also
requires `gold-eu-startups-searched-at.sql` before
`python -m huginn.elt.ingestion eu-startups-enrichment`. Existing databases
whose `ops.job_runs` check does not yet allow `skipped` must apply
`ops-job-runs-skipped-status.sql` before a command that records skipped
stages. Fresh installs already receive that status from `ops.sql`.

Apply each needed file once. The SQL is safe to rerun and preserves existing
data.

The tracking-fields file follows staging-table creation; it adds the raw EU
fields and their cross-source resolution columns. Discovery-only does not
read or write those Silver fields.

These match `docs/entities.md`, the [management foundation](../../docs/management-foundation.md), and the architecture document as of ADR-0002 and ADR-0011. Column-by-column Type 1/Type 2 classification beyond the two fields in `gold.company_history` is still open (Jira KAN-20); revise `gold.sql` and `src/huginn/elt/gold/dimensional.py` together when that lands.

## Upgrading a database that already exists

The seven files above are the fresh-install path. A schema change made after a database was created needs an `ALTER` file as well, or the change exists only for new installs and every existing deployment keeps the old shape. Apply the relevant `ALTER` files to an existing database, once each. They are idempotent and most are order-independent; `silver-eu-startups-tracking-fields.sql` requires `silver-eu-startups-listings.sql` to have created its table first. The superseded pair is another ordering case worth knowing about: `gold-company-yc-batch.sql` can add `yc_batch` and `gold-company-notes.sql` is what removes it, so whichever of the two runs last decides the outcome unless the successor creates `notes` unconditionally, which it does. The pair converges on `notes` in either order:

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
| `silver-eu-startups-listings.sql` | `silver.eu_startups_listings`, the per-source staging table for EU-Startups directory listings |
| `silver-eu-startups-tracking-fields.sql` | EU-Startups raw `founded`, `total_funding`, and `company_status` fields plus `founded` / `total_funding` on `silver.resolved_signals` |
| `gold-company-yc-batch.sql` | `gold.company.yc_batch`, superseded by `gold-company-notes.sql` |
| `gold-company-notes.sql` | `gold.company.notes` replaces `yc_batch`, rewriting existing values into source-prefixed form |
| `gold-drop-icp-filter-pass.sql` | drops `icp_filter_pass` from `gold.company` and `gold.company_history`, per ADR-0012 |
| `gold-rename-company-type-to-legal-form.sql` | `gold.company.company_type` renamed to `legal_form`, the axis the column actually holds |
| `gold-eu-startups-searched-at.sql` | `gold.company.eu_startups_searched_at`, the EU-Startups search cursor, per ADR-0010 |
| `ops-job-runs-skipped-status.sql` | `ops.job_runs.status` gains `'skipped'`, per ADR-0014's dependency-aware skip-on-failure policy |

The table contains seventeen upgrade files. They are idempotent:
re-running one on a database it has already been applied to is a no-op. Apply
only files whose changes are needed by the commands and schema version in use;
the full inventory is not a prerequisite list for every command. Automated
coverage of idempotency is much thinner than the sentence implies:

1. Four of the seventeen are executed against a real Postgres by a test: `gold-company-signal-source-stable-id.sql` by `tests/elt/gold/test_company_signal_migration.py`, `gold-business-sector-array.sql` by `tests/elt/gold/test_business_sector_array_migration.py`, `gold-eu-startups-searched-at.sql` by `tests/elt/gold/test_eu_startups_searched_at_migration.py`, and `silver-eu-startups-tracking-fields.sql` by `tests/elt/silver/test_eu_startups_tracking_migration.py`.
2. The other thirteen have no idempotency or upgrade-path test at all. Nothing in the suite can detect a reordering regression among them.
3. The fresh-install rebuild in CI is not a substitute for the missing tests. `tests/postgres_harness.py` applies the seven base files listed above and none of the seventeen additive upgrade files, reached through the `integration_database_url` fixture, so it exercises `gold.sql` and `silver.sql` as shipped and never an upgrade script.
4. `tests/elt/silver/test_upsert_sql_shape.py` is a different kind of check: it asserts the Silver upsert's column and placeholder parity as text and applies no schema file.

Three need a word of warning, because idempotent does not mean unconditional:

1. `gold-company-scale.sql` drops and recreates the `company_scale` CHECK. Re-running it after a future change to the band list validates existing values against the new list, so adding a band and backfilling it are two steps, and adding a band that existing rows violate fails loudly rather than silently dropping rows.
2. `gold-company-signal-source-stable-id.sql` refuses to run against a pre-ADR table that already has rows, because those rows have no `source_stable_id` and no correct value can be invented for one. `gold.company_signal` is a derived fact table, so the recovery is `TRUNCATE gold.company_signal` and a re-run of the Gold signal writer. It does not refuse a table that has the column, so re-running it after facts have accumulated is fine.
3. `gold-business-sector-array.sql` is guarded on the column's current type, not merely on its existence, and that guard is not optional. Re-applying `ARRAY[business_sector]` to a column that already holds `TEXT[]` wraps every value one dimension deeper, raising no error and leaving the column type at `text[]`. Its tests therefore assert `array_ndims` and the literal value, not just the type, because the type alone does not detect it.
