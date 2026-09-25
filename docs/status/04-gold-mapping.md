# Gold mapping: resolved_signals to company, history, and signal

Lead: Gold reads every `domain_normalized` row of Silver and builds or
updates one `gold.company` row per distinct domain. Per domain it writes
`domain` plus up to eight of the whitelisted columns, aggregated across
that domain's signals, and one of those, `business_sector`, is Type 2
tracked, so a sector change on an existing company does write a
`gold.company_history` row. `gold.company_signal` has a writer and holds
one fact row per signal. This file gives the read, the update rule, the
upsert mechanics, the history snapshot, the enrichment-candidate read
that feeds OpenCorporates ingestion, and the signal writer.

Files: `src/huginn/elt/gold/{models,company,company_signal,dimensional,ports}.py`,
`repositories/{company_repository,company_signal_repository}.py`. DDL:
`db/schema/gold.sql`. Decisions: ADR-0002 (current-plus-history split),
ADR-0007 (the `(source, source_stable_id)` idempotency key),
ADR-0008 (`icp_filter_pass` removed).

Every line citation below was opened and read at that line. Row counts are
from a read of the live development database on 2026-09-25.

## 1. CompanyWriter: the dimensional write path

`CompanyWriter.write_all()` (`company.py:160-219`):

1. Open one `with self._repository:` transaction
   (`company.py:191`), so the whole batch shares one connection and one
   transaction.
2. Read every domain-normalized signal: eight projected columns from
   `silver.resolved_signals`, `WHERE key_derivation = 'domain_normalized'
   ORDER BY resolved_at, id` (`company_repository.py:32-38`). Event grain:
   one row per signal. The `ORDER BY` makes the collapse deterministic,
   because all rows of one resolve batch share the same
   transaction-stable `resolved_at`, so `id` is what actually breaks the
   tie (`company_repository.py:22-31`).
3. Collapse to one record per domain (`company.py:194-213`). The collapse
   is per field, not per row: `name` keeps plain last-read-wins
   (`company.py:196`) because it is NOT NULL upstream and every signal
   carries one, while `stage`, `company_status`, `company_scale`,
   `business_sector`, `country`, `city`, and `notes` keep the last
   *non-null* value (`company.py:212-213`), because every HN signal has
   all seven as None by construction and a plain last-row-wins collapse
   would erase a YC company's values whenever an HN signal for the same
   domain is read after it.
4. For each domain: `write_company(self._repository, domain,
   new_values)` (`company.py:214-215`). `new_values` carries `name` plus
   whichever of the seven derived columns the signals supplied, so at
   most eight keys. `domain` is the separate first argument, never a key.
5. Resolved-only: a row whose key is `unresolved:...` is not a real
   company identity yet and never reaches Gold. Enforced by the read
   query's own WHERE clause, and restated in `company.py:126-132`.
   193 such rows sit in the live `silver.manual_review_queue`.

### The eight written columns

The seven derived ones are assigned in one tuple at `company.py:198-211`,
and `name` separately at `company.py:196`. All eight are read from Silver
through `DomainNormalizedSignal` (`models.py:23-35`) or computed from it.
Seven of the eight are source-specific, which is why the last-non-null
merge protects them; `name` is not merged that way.

| Column | Source | Derivation |
|---|---|---|
| `name` | `company_name_raw` | verbatim |
| `stage` | `stage` | verbatim |
| `company_status` | `company_status` | verbatim |
| `business_sector` | `industries` | `list(industries)`, Type 2 tracked |
| `notes` | `batch` | `f"YC {batch}"`, e.g. `YC Summer 2023` |
| `company_scale` | `team_size` | headcount bucketed into four bands |
| `country`, `city` | `all_locations` | first `City, Region, Country` entry split |

The three derivations that are not read straight off the signal, all
Huginn's vocabulary rather than a source's, live in Gold for that reason
(architecture doc 4.3):

1. `team_size_to_scale` (`company.py:27-46`) buckets the raw headcount
   into the four bands `db/schema/gold.sql:67-68` constrains.
2. `parse_all_locations` (`company.py:49-74`) splits the display string's
   first entry; a bare `Remote` or an empty string yields no value rather
   than a guess.
3. `notes` prepends a hardcoded `YC ` to YC's `batch`. The prefix is a
   label, not a merge key: `DomainNormalizedSignal` carries no `source`,
   so a second portal's batch would take the same last-non-null merge,
   overwrite YC's note, and be labelled `YC`.

`business_sector` is written whenever `industries is not None`, so an
empty `industries` array becomes `business_sector = []` rather than None
(`company.py:202-207`) and, on the last-non-null merge, an empty array
overwrites a known sector. No live row exercises that: all 4,337
populated `business_sector` values hold one or two entries.

## 2. The update rule: apply_company_update

Code `dimensional.py:41-55`, ADR-0002, architecture doc 4.3.

`TYPE_2_TRACKED_FIELDS = ("business_sector", "team_composition_signal")`
(`dimensional.py:15-18`): two entries, after ADR-0008 removed the third,
`icp_filter_pass`. Setting either to a value that differs from the current
row returns a `CompanyUpdate` with a `history_snapshot`: the superseded
values plus the current row's `id` (`dimensional.py:46-54`). The
comparison is presence-and-difference over `new_values`, so an absent key
is never a change. Any update that does not touch these two fields
returns `history_snapshot = None`: overwrite Company in place, no history
row.

Everything else on Company is Type 1: overwrite in place, no history
(ADR-0002). The exact column-by-column classification beyond these two
fields is still open (Jira KAN-20), though the column whitelist in
section 4 is de facto it for the writable set.

## 3. Write path: write_company

Code `company.py:77-119`.

1. `repository.get_company(domain)`: `SELECT id, business_sector,
   team_composition_signal, current_since FROM gold.company WHERE domain =
   %s FOR UPDATE` (`company_repository.py:44-49`). The `FOR UPDATE` locks
   the row so a concurrent writer cannot act on the same pre-update state
   (`company_repository.py:40-43`).
2. `apply_company_update(current or {}, new_values)`
   (`company.py:98-99`).
3. History decision: write a history row only when the company already
   exists (`current is not None`) and the update reports a Type 2 change
   (`company.py:107`). On first occurrence there is no prior version to
   supersede, and the snapshot's `company_id` (read from an empty current)
   would be NULL and violate `company_history.company_id NOT NULL`
   (`db/schema/gold.sql:103`).
4. `upsert_company(domain, result.new_values,
   bump_current_since=should_write_history)` (`company.py:108-110`).
5. When history applies: `insert_history(company_id, domain, snapshot,
   valid_from=current["current_since"])` (`company.py:112-119`), and the
   row's `valid_to` is the database's own transaction-stable `now()`,
   which matches the new `current_since` set by the same transaction's
   upsert (`ports.py:95-100`).

## 4. Upsert mechanics: build_upsert_query

Code `company_repository.py:115-164`. Two statement shapes, chosen by
whether `name` is in `new_values`.

1. The writable column list is `_COMPANY_COLUMNS` filtered by
   membership in `new_values` (`company_repository.py:145`). `domain` is
   never among them: it always comes from the function argument.
2. `_COMPANY_COLUMNS` (`company_repository.py:76-90`), thirteen names:
   `name`, `stage`, `company_status`, `business_sector`, `notes`,
   `company_scale`, `legal_form`, `country`, `city`, `address`,
   `phone_number`, `email`, `team_composition_signal`. (`legal_form` was
   `company_type` until commit `367f49a`.) Filtering is on membership in
   this tuple, so an unrecognized key in `new_values` is silently dropped
   and never interpolated into SQL text (BEST_PRACTICES.md 8.1).
3. With `name` present: `INSERT INTO gold.company (...) VALUES (...) ON
   CONFLICT (domain) DO UPDATE SET <present columns> =
   EXCLUDED.<column>` (`company_repository.py:147-156`). A new domain is
   inserted and an existing one updated in place, with no preceding read.
4. Without `name`: `UPDATE gold.company SET <present columns> = %s WHERE
   domain = %s` (`company_repository.py:158-164`). This shape exists
   because `name` is `gold.company`'s one NOT NULL column besides `domain`
   with no default (`db/schema/gold.sql:18`), and Postgres validates NOT
   NULL before ON CONFLICT is considered, so one statement cannot both
   insert and skip a column the caller does not have. An update-only
   write against a domain with no row therefore creates nothing, and
   `upsert_company` raises `ValueError` on a zero rowcount rather than
   letting a caller read a successful return as a write that happened
   (`company_repository.py:263-268`).
5. `current_since = now()` joins the SET list only when
   `bump_current_since` is true; `updated_at = now()` is always there
   (`company_repository.py:104-112`). A fresh INSERT already gets
   `current_since = now()` from the column default
   (`db/schema/gold.sql:93`), so the flag is not observable on insert.
6. Every column from `new_values` is a bind parameter, and `domain` is
   never duplicated inside `new_values`, so no caller string can reach
   either the ON CONFLICT target or the WHERE clause.

## 5. CompanyHistory snapshot

`_INSERT_HISTORY_SQL` (`company_repository.py:63-68`):

```
INSERT INTO gold.company_history
    (company_id, domain, business_sector, team_composition_signal,
     valid_from, valid_to)
VALUES (%s, %s, %s, %s, %s, now())
```

Five binds for six columns (`company_repository.py:277-285`): the six
columns are `company_id`, `domain`, the two superseded Type 2 values,
`valid_from`, and a database-clock `valid_to`.

One row per superseded version, window closed by `valid_to`; nothing in
this table is ever current, so no `is_current` flag (ADR-0002, which
rejects the single-table SCD Type 2 form for exactly this reason).

The mechanism is live, not inert. `business_sector` is Type 2 and is
written on 4,337 of 4,423 live companies, so a YC company whose
`industries` differ between two `write_all` runs writes a history row
carrying the superseded array. The table holds 0 rows today only because
no re-run has yet observed a change, which is a statement about the data,
not about the code. `team_composition_signal` is the other Type 2 field
and has never been written, so it cannot trigger one on its own: all
4,423 live rows sit at the column default `'unknown'`.

## 6. Enrichment candidate read (feeds OpenCorporates)

`EnrichmentCandidatePort.read_unenriched_company_names(limit)`
(`ports.py:132-150`), implemented structurally by
`PostgresCompanyRepository.read_unenriched_company_names`
(`company_repository.py:234-237`) over
`_READ_UNENRICHED_COMPANY_NAMES_SQL` (`company_repository.py:51-61`):

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

1. Candidates are companies whose `business_sector` is still NULL: that
   is both "never enriched" and a free enrichment-state marker, no extra
   column (fetch plan section 5).
2. Distinct by `name` (a domain can appear once but same-named rows
   collapse).
3. Returned oldest-created first, `id` as the deterministic tie-breaker,
   capped at the caller's run budget. In the real wiring
   (`__main__.py:48-56`) the budget is `OPENCORPORATES_MAX_CALLS = 50`
   (`__main__.py:27`).
4. 86 of 4,423 live companies match, all 86 of them companies only an HN
   signal knows about: each has an HN `company_signal` fact row and no YC
   one. The predicate still means "never enriched", but on current data it
   selects the HN-only tail rather than the whole table, because the
   4,337 companies with a YC fact row all carry a sector.

## 7. gold.company_signal: the fact table

Written by `CompanySignalWriter` (`company_signal.py:15-41`), which reads
every domain-normalized signal already joined to its `gold.company` row
and upserts one fact row per signal, event grain, deliberately not
collapsed (`company_signal_repository.py:19-25`).

1. The upsert is keyed on `(source, source_stable_id)`, Silver's own
   natural key, so a re-run of Silver's every-run reprocessing updates
   existing rows in place rather than duplicating them (ADR-0007,
   `company_signal_repository.py:27-38`). `id` and `ingested_at` are never
   in the `DO UPDATE SET` list.
2. Live: 4,431 rows, one per `domain_normalized` `resolved_signals` row
   (94 HN hiring, 1,478 YC hiring, 2,859 YC program_milestone). Every
   `gold.company` row has at least one.
3. Signals do leave Silver's event grain today. The read's inner join is
   what enforces the ordering, and it needs no coordination between the
   two writers: a signal whose `gold.company` row does not exist yet is
   simply not returned, and is picked up once Company catches up
   (`ports.py:115-121`).
4. Neither Gold writer is in the CLI composition root.
   `build_service` (`__main__.py:46-74`) wires the Bronze store, the
   three adapters, and the job-run writer. The one Gold object it
   constructs is `PostgresCompanyRepository`, used solely for the
   candidate read in section 6.

## 8. Columns no writer supplies

1. `legal_form`, `address`, `phone_number`, and `email` are in
   `_COMPANY_COLUMNS` and in the DDL, but nothing in the tree writes
   them: all four are NULL on all 4,423 live rows. They wait on a future
   writer (Jira KAN-43, enrichment), and `legal_form` on
   OpenCorporates specifically, which is the source that supplies it
   (`db/schema/gold.sql:86` and `db/schema/gold.sql:89-91`).
2. `team_composition_signal` is never written either, so all 4,423 rows
   sit at `'unknown'` (`db/schema/gold.sql:92`). It remains Type 2
   tracked. `icp_filter_pass` was on this list until ADR-0008 removed the
   column, since an ICP verdict is per-user and cannot live on a shared
   dimension.
3. Matching and scoring (the operational schema's writers) are not built
   anywhere (Jira KAN-18). `operational.users` exists only so the
   `operational.match` foreign key is valid (`db/schema/operational.sql`).
