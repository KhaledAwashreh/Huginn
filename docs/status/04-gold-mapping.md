# Gold mapping: resolved_signals to company and history

Lead: Gold reads only the `domain_normalized` rows of Silver and builds or
updates one `gold.company` row per distinct domain. Today it writes only
`domain` and `name`; the Type 2 history rule exists but nothing the current
pipeline writes can trigger it. This file gives the read, the update rule,
the upsert mechanics, and the enrichment-candidate read that feeds
OpenCorporates ingestion.

Files: `src/huginn/elt/gold/{models,company,dimensional,ports}.py`,
`repositories/company_repository.py`. DDL: `db/schema/gold.sql`. Decision:
ADR-0002.

## 1. CompanyWriter: the only Gold write path

`CompanyWriter.write_all()` (`company.py:75-98`):

1. Open one `with self._repository:` transaction.
2. Read every domain-normalized signal:
   `SELECT resolved_company_key, company_name_raw FROM silver.resolved_signals
   WHERE key_derivation = 'domain_normalized' ORDER BY resolved_at, id`
   (`company_repository.py:28-33`). Event grain: one row per signal. The
   `ORDER BY resolved_at, id` makes the collapse deterministic, because all
   rows of one resolve batch share the same transaction-stable
   `resolved_at` (`company_repository.py:22-26`).
3. Collapse to one record per domain, keeping the last
   `company_name_raw` in sort order (`company.py:90-92`): one read/write
   round-trip per distinct company, and only the last name would survive
   anyway under current-state semantics.
4. For each: `write_company(repository, domain, {"name": name})`.
5. Resolved-only: a row whose key is `unresolved:...` is not a real company
   identity yet and never reaches Gold (enforced by the WHERE clause, and
   restated in `company.py:56-63`).

The controller guarantees `key_derivation = 'domain_normalized'` rows carry
a domain key by construction (they were normalized from a real website, see
`03-silver-mapping.md`), so Gold treats `domain` as the durable natural key.

## 2. The update rule: apply_company_update

Code `dimensional.py:37-51`, ADR-0002, architecture doc 4.3.

`TYPE_2_TRACKED_FIELDS = ("business_sector", "team_composition_signal",
`team_composition_signal")` (`dimensional.py:14-17`). Updating either to
a value that differs from the current row returns a `CompanyUpdate` with a
`history_snapshot` (the superseded values plus the current row's `id`). Any
update that does not touch these fields returns `history_snapshot = None`:
overwrite Company in place, no history row.

Everything else on Company is Type 1: overwrite in place, no history. The
exact column-by-column classification beyond these two fields is still
pending the concrete schema (Jira KAN-20), though the column whitelist in
section 4 is de facto it for the writable set.

## 3. Write path: write_company

Code `company.py:16-50`:

1. `repository.get_company(domain)`: `SELECT id, business_sector,
   team_composition_signal, current_since FROM gold.company
   WHERE domain = %s FOR UPDATE` (`company_repository.py:39-45`). The
   `FOR UPDATE` locks the row so a concurrent writer cannot act on the same
   pre-update state.
2. `apply_company_update(current or {}, new_values)`.
3. History decision: write a history row only when the company already
   exists (`current is not None`) and the update reports a Type 2 change
   (`company.py:37-40`). On first occurrence there is no prior version to
   supersede, and the snapshot's `company_id` (read from an empty current)
   would be NULL and violate `company_history.company_id NOT NULL`.
4. `upsert_company(domain, new_values, bump_current_since=should_write_history)`.
5. When history applies: `insert_history(company_id, domain, snapshot,
   valid_from=current["current_since"])`, and the row's `valid_to` is the
   database's own transaction-stable `now()`, which matches the new
   `current_since` set by the same transaction's upsert
   (`ports.py:82-92`).

## 4. Upsert mechanics: build_upsert_query

Code `company_repository.py:97-136`.

1. Build the writable column list as `domain` (always, from the function
   argument, never from `new_values`) plus the columns of
   `_COMPANY_COLUMNS` present in `new_values`.
2. `_COMPANY_COLUMNS` (`company_repository.py:72-83`): `name`,
   `business_sector`, `company_type`, `country`, `city`, `address`,
   `phone_number`, `email`.
   Columns are whitelist-filtered in code before any name reaches SQL text:
   an unrecognized key in `new_values` is silently dropped, never
   interpolated (BEST_PRACTICES.md 8.1).
3. `INSERT ... ON CONFLICT (domain) DO UPDATE SET <present columns> =
   EXCLUDED.<column>, updated_at = now()`. `current_since = now()` is added
   to the update branch only when `bump_current_since` is true. A fresh
   INSERT already gets `current_since = now()` from the column default
   (`db/schema/gold.sql`), so the flag is not observable on insert.
4. Every column from `new_values` is a bind parameter. `domain` is never
   duplicated inside `new_values`, so a caller cannot silently produce an
   INSERT missing the NOT NULL `domain`.

## 5. CompanyHistory snapshot

`_INSERT_HISTORY_SQL` (`company_repository.py:59-64`):

```
INSERT INTO gold.company_history
  (company_id, domain, business_sector, team_composition_signal,
   valid_from, valid_to)
VALUES (%s, %s, %s, %s, %s, %s, now())
```

One row per superseded version, window closed by `valid_to`; nothing in
this table is ever current, so no `is_current` flag (ADR-0002).

Displayed consequence in the current pipeline: `CompanyWriter` only ever
passes `{"name": name}` to `write_company`, and `name` is not Type 2, so no
run of the current code writes a `company_history` row. The history
mechanism is fully implemented but inert until a writer supplies a Type 2
field (the future enrichment writer for `business_sector`, per the
KAN-53/54 branch's own design).

## 6. Enrichment candidate read (feeds OpenCorporates)

`EnrichmentCandidatePort.read_unenriched_company_names(limit)`
(`ports.py:95-112`), implemented by `PostgresCompanyRepository`
(`company_repository.py:197-200`):

```
SELECT name FROM (
  SELECT DISTINCT ON (name) name, created_at, id
  FROM gold.company
  WHERE business_sector IS NULL
  ORDER BY name, created_at, id
) AS distinct_companies
ORDER BY created_at, id
LIMIT %s
```

1. Candidates are companies whose `business_sector` is still NULL: that is
   both "never enriched" and a free enrichment-state marker, no extra
   column (fetch plan section 5).
2. Distinct by `name` (a domain can appear once but same-named rows collapse).
3. Returned oldest-created first, `id` as the deterministic tie-breaker,
   capped at the caller's run budget. In the real wiring
   (`__main__.py:48-56`) the budget is `OPENCORPORATES_MAX_CALLS = 50`.
4. Because nothing ever sets `business_sector`, every company stays an
   enrichment candidate indefinitely until an enrichment consumer lands.

## 7. The empty surface: gold.company_signal and beyond

1. `gold.company_signal` is fully defined in DDL (`db/schema/gold.sql`) but
   has no reader or writer in this tree. The writer is being built on the
   parallel branch `gold/kan-41-company-signal-writer` (unmerged). No
   signal currently leaves Silver's event grain.
2. No Gold code reads `company_type`, `country`, `city`, `address`,
   `phone_number`, `email`, `team_composition_signal`, or
   They sit at column defaults (`team_composition_signal = 'unknown'`) until a
   future writer (Jira KAN-43, enrichment) supplies them. `icp_filter_pass` was
   on this list until ADR-0008 removed the column, since an ICP verdict is
   per-user and cannot live on a shared dimension.
3. Matching and scoring (the operational schema's writers) are not built
   anywhere (Jira KAN-18). `operational.users` exists only so the
   `operational.match` foreign key is valid (`db/schema/operational.sql`).