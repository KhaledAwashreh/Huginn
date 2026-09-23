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

`ON_ERROR_STOP` and the single transaction make any SQL error fail the
bootstrap without committing a partial schema. The management development
database still receives every ELT schema because retained operational tables
reference `gold.company`. Use a new, dedicated, disposable database; this
bootstrap does not authorize dropping or resetting an existing database.

## Existing Pre-KAN-83 Databases

KAN-83 has one idempotent additive upgrade for a database with the prior
Bronze schema. It creates only the EU-Startups discovery state/retry tables
and their supporting indexes; it does not alter or remove existing data:

```bash
rtk proxy psql "$HUGINN_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f db/schema/kan-83-eu-startups-discovery.sql
```

Run it once before invoking `python -m huginn.elt.ingestion eu-startups-discovery`
against a pre-KAN-83 database. This is deliberately a one-off additive
deployment step for KAN-83, not a general migration framework or a precedent
for versioned upgrades. The MVP's existing data is disposable, but this SQL is
safe to rerun and preserves it.

These match `docs/entities.md`, the
[management foundation](../../docs/management-foundation.md), and the
architecture document as of ADR-0002 and ADR-0011. Column-by-column Type 1/Type
2 classification beyond the three fields in `gold.company_history` is still
open (Jira KAN-20); revise `gold.sql` and
`src/huginn/gold/dimensional.py` together when that lands.
