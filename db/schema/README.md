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
