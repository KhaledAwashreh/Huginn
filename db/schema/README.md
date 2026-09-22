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

`ON_ERROR_STOP` and the single transaction make any SQL error fail the
bootstrap without committing a partial schema. The management development
database still receives every ELT schema because retained operational tables
reference `gold.company`. Use a new, dedicated, disposable database; this
bootstrap does not authorize dropping or resetting an existing database.

These match `docs/entities.md`, the
[management foundation](../../docs/management-foundation.md), and the
architecture document as of ADR-0002 and ADR-0011. Column-by-column Type 1/Type
2 classification beyond the three fields in `gold.company_history` is still
open (Jira KAN-20); revise `gold.sql` and
`src/huginn/gold/dimensional.py` together when that lands.
