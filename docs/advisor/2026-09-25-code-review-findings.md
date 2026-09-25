# Huginn Code Review Findings

Date: 2026-09-25

Commits reviewed: `66a1dcb`, `63ea2fc`, `1bb0f54`, `79590ef`, `1402f65`, `648d20e`
(branch `ingestion/kan-53-54-opencorporates-adapter`, tip `648d20e`).

Method: four independent review subagents over disjoint areas (schema and
migrations, documentation accuracy, Gold layer, test infrastructure and
coverage), each told to report findings only and to verify against the live
database rather than infer. Suite at time of review: 332 passed, 0 skipped.
Ruff check and format clean.

Status: **nearly all fixed**. 27 of 34 entries are fixed (see each entry).
Remaining open: SCHEMA-03, TEST-05, TEST-06, TEST-07, TEST-08, TEST-09,
TEST-10, and the untested-surface list, none of which break anything at
runtime. Each defect has a
stable ID so they can be worked one at a time; the ID is the reference to use
in commit messages.

## Executive summary

| Area | High | Medium | Low |
| --- | --- | --- | --- |
| Schema and migrations | 0 (1 fixed) | 0 (1 fixed) | 0 (2 fixed) |
| Documentation accuracy | 0 (5 fixed) | 0 (8 fixed) | 0 |
| Gold layer | 0 | 0 (1 fixed) | 0 (5 fixed) |
| Test infrastructure | 0 (2 fixed) | 0 (2 fixed) | 4 open |
| Refuted data claims in SQL comments | 0 | 0 | 0 (4 fixed) |

The single highest-severity defect is a migration-ordering bug that makes an
upgraded database unusable while reporting success. The documentation findings
are numerous but concentrated: five files under `docs/status/` describe a tree
that no longer exists, and several SQL comments cite live row counts and data
shapes that the live data refutes.

## Disclosure: a review agent wrote to the development database

While proving the isolation tripwires actually fail on the original bug, the
test-infrastructure reviewer copied `tests/` to `/tmp/opencode/revert-sim/`
with a conftest reproducing the old short-circuit and ran it. That rewrote the
dev database: `gold.company.max(updated_at)` moved from
`2026-09-25 20:40:00.313193+00:00` to `2026-09-25 20:46:09.204621+00:00`. Row
counts were identical before and after (4,423), no rows were added or removed,
and no scratch database was created by that run. The run also left a
`scratch_legacy` database on the dev server, which the reviewer did not drop
because dropping is a write. It could not be attributed to any code in this
repo or in `.worktrees/kan-83-eu-persistence`.

This is the reported harm reproduced deliberately, which is the strongest
available evidence the tripwire works. It has not been independently verified.

Separately, and predating this review: the original, pre-fix test suite had
already rewritten the dev `gold.company` dimension during ordinary `pytest`
runs, before the isolation fix landed. The data was rebuilt afterwards.

## High severity

### SCHEMA-01: FIXED. the notes/yc_batch migration pair is order-dependent, and the losing order is the documented one

`db/schema/gold-company-notes.sql:42-44` returns early when `yc_batch` is
absent. `db/schema/gold-company-yc-batch.sql:27-34` yields only when `notes`
already exists. Migrations apply in filename order, and `notes` sorts before
`yc-batch`, so on a legacy database the superseded file runs last and wins.

Reproduced by the reviewer on a database built from the real pre-`1bb0f54`
base files plus seed data, applying all twelve ALTERs in filename order:

```
gold.company has: ['yc_batch']          # notes never created
real Gold writer upsert: FAIL -> UndefinedColumn: column "notes" does not exist
```

The migration set exits 0 and reports no error. A second pass repairs it,
because on that pass `yc_batch` exists when `notes` runs, which is worse than a
clean break: the undocumented remedy is to re-run what the README says to run
once. An exhaustive test of all 66 migration pairs in both orders found this to
be the only divergent pair.

Concrete impact: `company_repository.py:81` lists `notes` in
`_COMPANY_COLUMNS` and `company.py:215` supplies it, so the first Gold
dimension write of any company dies on an upgraded database.

Two comments assert the opposite of what was measured:

1. `db/schema/gold-company-yc-batch.sql:21` claims "Yielding when notes exists
   makes the pair order-independent." True only when `gold.sql` has already
   supplied `notes`, which is the fresh-install case. False for the upgrade
   path, the only path this file exists for.
2. `db/schema/README.md:20` says "Apply the relevant `ALTER` files to an
   existing database, in any order, once each."

The live `huginn` database is correct only by accident of commit order:
`gold-company-notes.sql` landed in `1402f65`, after `gold-company-yc-batch.sql`
in `1bb0f54`, and was applied on top of an already-migrated table.

### TEST-01: FIXED. the behavioural isolation tripwire can never fail in CI

`tests/test_integration_database_isolation.py:60-66`. CI no longer sets
`HUGINN_DATABASE_URL`, so `developer_url is None` and the test skips. Verified
with a faithful CI simulation (copy of `tests/`, `db/`, `src/`, no `.env`,
variable unset, real container): 331 passed, 1 skipped, exit 0. `.env` is
gitignored, so nothing reloads it on a runner.

A pull request that reinstates the original short-circuit therefore merges
green and is discovered only on a developer's machine.

**Fixed.** The guard no longer reads the environment. `conftest.py` stamps the
database it provisions with `COMMENT ON DATABASE`, and the test asserts the
stamp is present, which is positive evidence of provenance available
identically on a laptop and a runner. Verified: 2 passed with the variable unset
and no `.env` reachable, where the old version skipped; and with the original
short-circuit reinstated, the guard fails with an explicit message.

### TEST-02: FIXED. an unavailable Docker daemon yields a green run with 14% of the suite unexecuted

`tests/conftest.py:58-83`. Verified by pointing `DOCKER_HOST` at a dead socket:
286 passed, 46 skipped, exit 0. All 45 integration and migration tests plus the
behavioural tripwire disappear, including every real-SQL and every migration
test. Skipping on unavailable Docker is the stated intent and is correct; the
defect is that nothing distinguishes "Docker unavailable" from "the tests ran",
so a Docker Hub pull failure or rate limit on a runner produces a green build
with the meaningful tests silently absent.

**Fixed.** The fixture now calls `pytest.fail` instead of `pytest.skip`. Because
it is session-scoped and only integration tests request it, the failure is
confined to them. Verified with `DOCKER_HOST` pointed at a dead socket:
`286 passed, 46 errors`, exit code 1. The DB-free unit tests still run and
still pass, and CI goes red.

### DOC-01: FIXED. `docs/status/04-gold-mapping.md` describes the pre-change Gold writer throughout

The file advertises itself as a code-verified map. It is wrong in its lead,
read, write, allowlist, SQL and conclusions. `company.py` changed by 158 lines
and `company_repository.py` by 46 in the change under review; this file was not
updated for either.

| Line | Claim | Reality |
| --- | --- | --- |
| 4-5 | writes only `domain` and `name`; nothing written can trigger the Type 2 rule | `company.py:203-216` writes seven more columns per signal; 4,337 live rows carry `notes` |
| 20-21 | SELECT projects two columns | `company_repository.py:33-37` projects eight |
| 27 | collapse keeps the last `company_name_raw` | collapse is per field; seven fields keep the last non-null value |
| 30 | passes `{"name": name}` | passes a nine-key `new_values` |
| 33 | unresolved exclusion at `company.py:56-63` | that range is the `parse_all_locations` docstring; the claim is now at `136-141` |
| 43-44 | `TYPE_2_TRACKED_FIELDS` lists `team_composition_signal` twice | `dimensional.py:14-17` has two entries, and the same file says "two fields" at line 52 |
| 84-86 | `_COMPANY_COLUMNS` has eight names | `company_repository.py:76-90` has thirteen |
| 104-108 | history INSERT quoted as seven values for six columns | actual is five values for six columns; the quoted SQL would raise a Postgres arity error |
| 113-118 | history mechanism "fully implemented but inert" | `business_sector` is Type 2 and is written; a sector change now writes history |
| 144-145 | "nothing ever sets business_sector", every company stays an enrichment candidate | 86 of 4,423 are NULL; the predicate's meaning has inverted to mostly "HN-only company" |
| 149-152 | `gold.company_signal` has no writer, built on an unmerged branch | `gold/company_signal.py` is in the tree (`ec14426`, `e9e8207`); 4,431 live rows |
| 153-155 | no Gold code reads `country` or `city` | both written; 4,244 and 4,196 non-null |
| 16, 41, 59, 79, 101, 122 | seven line citations | all wrong; only `dimensional.py:14-17` is still right |

The lead sentence is a false statement in correct form, which is the most
expensive kind of drift: a reader gets the opposite of the truth on the file's
central subject.

### DOC-02: FIXED. `docs/status/03-silver-mapping.md` omits the six fields and denies the filter exists

| Line | Claim | Reality |
| --- | --- | --- |
| 47-48 | "Never returns None" | `yc_staging.py:62-63` returns `None` for Acquired/Inactive; 1,903 rows skipped |
| 50-59 | Bronze-field to staging-column table, 8 rows | omits `company_status`, `team_size`, `industries`, `all_locations`, `former_names`, `batch` |
| 66-79 | both staging upserts "identical shape", 8 columns | YC inserts 14, HN inserts 8 |
| 123-124 | `resolved_signals` upsert has 10 columns | 16 columns |
| 25, 155-158 | 282 bronze HN rows became 260 staging; YC 6204 | 301 to 273; YC 4,349 of 6,252 |
| 160-166 | counts derived from a pre-rename `match_confidence` schema | no such column; live is `domain_normalized` 4,431, `unresolved` 193 |

Section 1.2 is titled as the authoritative Bronze-to-YC-staging map, which is
the one place a reader would look for the new fields.

### DOC-03: FIXED. `docs/status/00-repo-and-run-status.md` is wrong in four of five sections

| Line | Claim | Reality |
| --- | --- | --- |
| 5 | "a live dev database one schema version behind the DDL" | database is current |
| 12 | tip `ff3bf78`, 8 commits ahead of master | tip `648d20e`, 18 commits ahead |
| 16-28 | "Unmodified on this branch relative to master: all Silver code, `db/schema/*`" | this branch modifies 8 Silver modules, 6 Gold modules, 13 schema files |
| 79-86 | `gold.company` has **0 rows**; `ops.job_runs` 6 | 4,423 and 19 |
| 81 | `silver.yc_listings` 6204, "1:1 with bronze yc rows" | 4,349, and it contradicts `docs/entities.md:145` in the same repo |
| 103-108 | "9 integration tests fail locally; the pipeline works only as far as the staging tables" | 332 passed, 0 failed; pipeline reaches 4,423 companies and 4,431 signals |
| 110-112, 135-137 | CI applies the DDL to a Postgres 16 service | that block was deleted in `79590ef` |
| 64-69 vs 138-139 | untracked files list contradicts itself | `docs/status/04-gold-mapping.md` is now committed |
| 144-145 | company signal writer "separate branch, not merged" | merged on this branch |

### DOC-04: FIXED. `docs/status/README.md` key facts 2, 3 and 5 are refuted

| Line | Claim | Reality |
| --- | --- | --- |
| 3-4 | "snapshot at commit `ff3bf78`"; "every claim checked against the code" | tip is `648d20e`; the drift above is the counter-evidence |
| 53-55 | pipeline writes only `domain` and `name`; everything else at default | refuted as in DOC-01; also self-contradicting, since KAN-41 has landed |
| 56-57 | `gold.company_signal` "no code reads it or writes it" | writer exists; 4,431 rows |
| 60-63 | dev DB on a pre-rename schema; nine tests fail; CI applies DDL | migrated; 332 passed; CI uses testcontainers |
| 42 | diagram: company_signal "table exists, no writer" | writer exists |

### DOC-05: FIXED. ADR-0008's own consequence is contradicted by the same commit

`adr/0008-icp-verdict-not-on-company-dimension.md:76-79`, consequence 5:

> "If `team_composition_signal` is never populated either, the history table
> stays empty, which is already true today."

`business_sector` **is** populated by the same change (`company.py:207-212`)
and is Type 2 (`dimensional.py:14-17`). A YC company whose `industries` change
between two `write_all` runs writes a history row. The stated condition is
therefore the wrong one: `team_composition_signal` being unpopulated does not
keep the table empty. The table is empty today only because no re-run has
observed a change, which the ADR does not distinguish from "cannot happen".

## Medium severity

### SCHEMA-02: FIXED. the two install paths never converge on the `company_scale` CHECK

`db/schema/gold.sql:60` declares the CHECK inline, so a fresh install gets the
auto-generated name `company_company_scale_check`.
`db/schema/gold-company-scale.sql:37-42` drops `company_scale_check` (absent on
that path, so the `IF EXISTS` drop no-ops) and adds `company_scale_check`.

```
fresh install only:                 ['company_company_scale_check']
fresh install + gold-company-scale: ['company_company_scale_check', 'company_scale_check']
migrated + gold-company-scale:      ['company_scale_check']
```

Inert while the band list is unchanged, but the two constraints are not updated
together. Simulating the next band change (`'5001+'` added):

```
fresh install path: insert company_scale='5001+' -> REJECTED
migrated path:      insert company_scale='5001+' -> OK
```

`gold-company-signal-source-stable-id.sql:73-74` deliberately names its
constraint to avoid exactly this, so `gold-company-scale.sql` breaks a
convention the repo already established. Nothing references either name today,
so this is latent.

### GOLD-01: FIXED. a Type-2-only write fails against real Postgres, and the test advertising that shape only asserts SQL text

`company_repository.py:120-143`. `build_upsert_query` hardcodes `domain` into
the column list because it is NOT NULL and the ON CONFLICT target, and the
docstring at `108-114` explains the hazard: Postgres validates NOT NULL before
ON CONFLICT is considered. `name` (`gold.sql:18`) is also NOT NULL and gets no
equivalent treatment.

Reproduced against a throwaway Postgres loaded from `db/schema/gold.sql`:

```
tcs-only write on an EXISTING row FAILED: NotNullViolation
tcs-only write on a NEW domain     FAILED: NotNullViolation
```

The failure mode is the point: the INSERT branch is attempted and rejected even
though a row exists and only the UPDATE branch should run, aborting the whole
`write_all` transaction.

Pre-existing (`6a5a324`), so not a regression from this change, and unreachable
today because `CompanyWriter.write_all` is the only caller and always sets
`values["name"]` (`company.py:201`). But
`tests/elt/gold/test_company_repository.py:24-31` names this exact shape as a
supported caller, asserts only on SQL text, and never executes it. The KAN-43
enrichment writer that `bump_current_since` exists for is the obvious next
caller.

### TEST-03: FIXED. the static tripwire's regex misses the most obvious bypass

`tests/test_integration_database_isolation.py:34-36` matches only
`os.environ.get(` and `os.environ[`. Verified misses: `os.getenv(...)`,
`from os import environ` plus `environ[...]`, `from os import getenv`,
`dotenv_values()[...]`. A module using `os.getenv` was placed in the
simulation tree and the static test still passed. The docstring at line 88
claims no module may read the variable, which is broader than the pattern
enforces.

**Fixed.** The check now matches the bare string `HUGINN_DATABASE_URL` rather
than a set of call patterns, so it closes the class rather than the instances:
every route to the value has to name it somewhere. Verified that both
`os.getenv` and a from-import are caught.

### TEST-04: FIXED. only `name` is ever written to a real `gold.company`, and the intended guard is self-referential

`company_repository.py:76-90` allowlists thirteen columns, but
`tests/elt/gold/test_company_integration.py:46-83` is the only test that runs
`build_upsert_query`'s SQL against the real table, and its `new_values`
contains only `name`. Its signal sets no `stage`, `status`, `team_size`,
`industries`, `all_locations` or `batch`, so `company.py:217-218` omits them
all. `stage`, `company_status`, `business_sector`, `notes`, `company_scale`,
`country`, `city`, `address`, `phone_number`, `email` and
`team_composition_signal` are never touched by a real statement.

The intended guard, `tests/elt/gold/test_company.py:417-450`, compares the
writer's keys against `_COMPANY_COLUMNS` and against an INSERT list built from
that same tuple, so a name wrong in both places passes. Concretely: rename
`notes` in `db/schema/gold.sql:70` and not in `_COMPANY_COLUMNS` (the exact
shape of the `yc_batch` to `notes` rename) and every test stays green while
`write_all()` raises `UndefinedColumn` on the first real ingest.

### TEST-05: neither new migration has a test, and ten of twelve ALTER files are never executed

`db/schema/gold-company-notes.sql` and `db/schema/gold-drop-icp-filter-pass.sql`
have no coverage. Only `gold-business-sector-array.sql` and
`gold-company-signal-source-stable-id.sql` do.
`tests/conftest.py:32-39` applies only the six CREATE files, never the ALTER
set, so nothing in the suite can detect a reordering regression, which is why
SCHEMA-01 is uncaught.

The `'YC ' || yc_batch` conversion is asserted nowhere. Nothing pins the
absence of `icp_filter_pass`, and re-adding it to `TYPE_2_TRACKED_FIELDS` is
behaviourally inert because no writer puts the key in `new_values`
(`dimensional.py:46` requires `field in new_values`), so ADR-0008's decision can
be silently reversed with a green suite.

### SCHEMA-03: the `business_sector` type guard is narrower than the change it guards

`db/schema/gold-business-sector-array.sql:42-46` tests `data_type = 'text'` on
`gold.company` only, then alters `gold.company_history` inside the same `IF`.
Two silent no-op states:

1. A pre-migration column of any other scalar type (`character varying`,
   `bpchar`, a domain) makes `is_still_scalar` false, so the block does nothing
   and the database keeps a scalar `business_sector` while `gold.sql:48`
   promises `TEXT[]`.
2. `gold.company` already `TEXT[]` but `gold.company_history` still `TEXT`: the
   guard is false, the block is skipped, and the two tables keep different types
   while `gold.sql:48` and `gold.sql:97` both declare `TEXT[]`.

Neither is reachable from the current files, so this is low, but it is the same
class as the bug the guard was written to prevent.

### SCHEMA-04: FIXED. `db/schema/README.md:41` overstates migration test coverage

Says the ALTER files are covered by named tests "and by the fresh-install
rebuild in CI for the rest". The fresh-install path is the six base files, so it
exercises `gold.sql`/`silver.sql`, not the twelve ALTER scripts. Ten of twelve
have no automated idempotency or upgrade-path coverage.

### DOC-06: FIXED. `docs/architecture.md:145` still keeps the ICP gate ADR-0008 asked to be reworded

The commit correctly rewrote lines 147 and 152 but left 145, which still says
the team-composition heuristic is "run only on companies that already passed the
ICP filter". ADR-0008:89-91 named this exact sentence as needing rewording.

Also on this file: line 34 "Ingestion from exactly two sources" contradicts
lines 1, 11 and 131, which all name three including OpenCorporates (pre-existing).
Section 13 item 9 lists only `adr/0001` and `adr/0002` as the decision records
for the Silver and Gold designs, while `adr/0008` is a Gold decision the body
now depends on.

### DOC-07: FIXED. wrong module path in two authoritative files

`db/schema/gold.sql:7` and `db/schema/README.md:16` both cite
`src/huginn/gold/dimensional.py`, which does not exist. The real path is
`src/huginn/elt/gold/dimensional.py`.
`db/schema/silver-yc-former-names.sql:6` cites `silver/elt/resolution.py`; the
real path is `src/huginn/elt/silver/resolution.py`.

### DOC-08: FIXED. `signal_resolution_repository.py:20-23` says four columns above a SELECT that projects six

The comment reads "only silver.yc_listings has a registry status, a headcount,
an industry list, and a location, so those four columns are projected here and
not there." The select at lines 24-29 projects `company_status`, `team_size`,
`industries`, `all_locations`, `former_names`, `batch`. The prose stops at
`all_locations` and never reaches the two newest fields, which is what makes
the "wider by design" framing misleading.

### DOC-09: FIXED. `entities.md` and `silver.sql` carry four wrong counts

| Claim | Location | Reality |
| --- | --- | --- |
| "former_names ... present on 3,054 of 6,252 live rows" | `entities.md:156`, `silver.sql:57` | 3,054 is the **bronze** count of rows with a non-empty value. On `silver.yc_listings` the column is non-null on 4,349 rows, of which **2,064 are empty arrays**. Neither doc discloses the empty-array case, which is the very distinction `yc_staging.py:30-36` preserves. |
| "51 distinct live values ... plus one row reading Unspecified" | `entities.md:157`, `silver-yc-batch.sql:24` | `silver.yc_listings.batch` has **49** distinct values. 51 is the bronze count. `Summer 2005` and `Winter 2006` are entirely absent from Silver because all their rows are Acquired/Inactive. Also reads as 52, since Unspecified is inside the 51. |
| "These four are YC-only ... minus these five" | `entities.md:168` | six columns are YC-only. Both counts are wrong and contradict each other in adjacent sentences. |
| "industries verbatim: a list on 78% of live rows" | `silver.sql:47` | the key is present on 6,252 of 6,252. 78.4% is the **more-than-one-industry** share, which `gold.sql:40` states correctly. Two files took one number for two different facts. |

Separately, `entities.md:133` says "~11% of sampled HN posts have no
extractable URL" where the live figure is 178 of 273, **65%** (pre-existing).

### DOC-10: FIXED. `parse_all_locations` documents bronze populations and one unreproducible number

`src/huginn/elt/gold/company.py:49-70`. The docstring opens "confirmed on all
6,252 live rows", a bronze population, inside a Gold function whose input is
Silver's 4,349 rows.

- 154 empty and 44 bare `Remote` are **bronze** counts. The Silver equivalents
  are 65 and 29.
- "which is 203 live rows" for the no-city case is not reproducible. Applying
  the function's own condition gives 63 in bronze and 48 in Silver. Six nearby
  interpretations were tested and none produce 203.

Under the repo's "docstrings cite, they don't restate" rule this is also a
standards violation: 21 lines of prose explaining what the parse does, with no
citation.

### DOC-11: FIXED. `docs/status/05-orchestration-config-ops.md` §6 and §7.5 are superseded

| Line | Claim | Reality |
| --- | --- | --- |
| 134-140 | conftest starts a container "when `HUGINN_DATABASE_URL` is not already reachable" and "redirects the env var"; "a live reachable database is used as-is" | inverted in every clause. `conftest.py:1-9` says "provisioned here, never discovered"; there is no reachability probe; the fixture never writes `os.environ`; a start failure skips rather than falling back |
| 118 | 31 test files | 36 |
| 120-124 | "212 passed, 9 failed, all against the stale local schema" | 332 passed, 0 failed |
| 155-156 | CI runs against a Postgres 16 service with fresh schema | deleted in `79590ef` |

### DOC-12: FIXED. `docs/status/01-source-field-registry.md` §2.3 omits every field Silver reads

The section promises "exactly which fields the code reads and where each one
goes" and lists four adapter reads, all in `yc.py`. Thirteen more are read by
`yc_staging.py:65-81` and none appear. Combined with DOC-02, **no document in
`docs/status/` maps any of the six new fields from the Bronze payload to a
Silver column.**

### GOLD-02: FIXED. stale "three" count for the Type 2 fields, twice

`src/huginn/elt/gold/dimensional.py:6` says "The exact column-by-column
classification beyond these **three** fields is pending the concrete schema
(Jira KAN-20)". The tuple eight lines below has two. `648d20e` updated the tuple
and the docstring beneath it, not the module docstring above.
`tests/elt/gold/test_company.py:396` says the same thing. Also "pending the
concrete schema" is stale independently: `db/schema/gold.sql` exists.

### GOLD-03: FIXED. `company.py` cites a function that no longer exists

`src/huginn/elt/gold/company.py:159` ends "first (see build_source_note)". That
function was deleted in `1402f65` when the prefixing was inlined;
`build_source_note` appears nowhere in `src/` or `tests/`. Under CLAUDE.md code
standard 3 a docstring citation is a promise the target exists.

### GOLD-04: FIXED. `company.py` claims a second-portal property the code does not have

`src/huginn/elt/gold/company.py:157-159` says `notes` is assembled "from a
source's own value plus a source prefix, so a second portal's contribution is
attributable rather than overwriting the first". With one hardcoded `"YC "`
prefix at line 215 and no `source` on `DomainNormalizedSignal`, a second
portal's batch would take the last-non-null merge and **overwrite** the YC note,
and would be labelled `YC`. The code is the deliberate tradeoff `1402f65`
records; only the docstring overclaims. The same overclaim is at
`db/schema/gold.sql:65-67`.

## Low severity

### GOLD-05: FIXED. dangling comma from the deleted middle item

`src/huginn/elt/gold/company.py:146` reads "ResolvedSignal carries no
team_composition_signal, or contact field." The comma belonged to the deleted
`icp_filter_pass`. Content is correct; punctuation is not.

### GOLD-06: FIXED. "Two" where three derivations are described

`src/huginn/elt/gold/company.py:151` says "Two of the derivable ones are not
read from resolved_signals directly" then describes three: `company_scale`,
`country`/`city`, and `notes`. Pre-existing wording; the third was added by
`1402f65` without updating the count.

### GOLD-07: FIXED. em dash in a test docstring

`tests/elt/gold/test_company_repository.py:27`. Pre-existing (`6a5a324`).

### SCHEMA-05: FIXED. refuted data claims in SQL comments

| Claim | Location | Reality |
| --- | --- | --- |
| "every batch from Summer 2005 to Winter 2011 has its earliest `launched_at` on exactly 2012-01-17" | `silver-yc-batch.sql:11-13`, `gold-company-notes.sql:15-16` | 12 of 13 match. **Summer 2008's earliest is 2010-01-17** (1 row there, 21 at 2012-01-17) |
| "Oklo is 'Public' while every other company in the dev database is 'Active'" | `gold-company-status.sql:8-11` | 23 Public (Airbnb, Coinbase, DoorDash, GitLab, Instacart, Oklo and others), 4,314 Active, 86 NULL |
| "Every live value is currently NULL" for `business_sector` | `gold-business-sector-array.sql:17-18` | 4,337 of 4,423 populated, all one-dimensional |
| "6,204 live populated rows" | `gold-business-sector-array.sql:30-31` | no subset matches: bronze YC 6,252, gold populated 4,337, silver populated 4,349. Unreproducible |
| "6,298 domain_normalized, 229 unresolved today" | `silver-yc-former-names.sql:7` | 4,431 and 193 |

The Summer 2008 error matters more than the others: it is the evidence sentence
for the central claim that `batch` and `launched_at` are independent, and one
thirteenth of it is wrong.

### TEST-06: the limit test contradicts its own comment and asserts almost nothing

`tests/elt/gold/test_company_repository_integration.py:99-123`. The comment at
21-27 says every fixture is pinned to `_EPOCH` so assertions hold regardless of
session leftovers, but line 111 uses `now + timedelta(seconds=i)`. The
assertion is `len(names) <= 2` with no check on which names returned. Drop the
`LIMIT` and, with fewer than three unenriched rows present, it still passes.

### TEST-07: a duplicated test whose only extra assertion restates dataclass defaults

`tests/elt/silver/test_upsert_sql_shape.py:127-145`.
`test_resolved_record_exposes_every_field_the_upsert_binds` repeats the same
set equality as `test_upsert_binds_exactly_the_fields_the_record_declares`
against the same SQL. Its remaining assertion,
`record.industries is None and record.former_names is None`, guards nothing
about the pipeline.

### TEST-08: the resolver's positional row mapping has no static counterpart

`src/huginn/elt/silver/repositories/signal_resolution_repository.py:57-93`,
indices at 73-76. The Gold read got a dedicated distinct-marker test
(`test_company_repository_integration.py:126-188`); the resolver's
`_YC_STAGING_SELECT_SQL` to index mapping got nothing equivalent, even though
`test_upsert_sql_shape.py` exists for that drift class on the write side.
Adjacent swaps are caught, but only by tests that skip entirely without Docker
(TEST-02).

### TEST-09: the tripwire only knows about the one database the environment names

`tests/test_integration_database_isolation.py:60-84`. The dev server holds five
non-template databases besides `huginn`. A regression pointing the suite at a
different real developer database passes. A design limit of the invariant as
stated.

### TEST-10: the fixture logs a DSN containing a password

`tests/conftest.py:101`. pytest prints captured logs on failure. The credential
is throwaway in an ephemeral container, but the tripwire deliberately avoids
echoing the developer URL (lines 70-76), so the contrast is worth noting.

## Untested surface

No defect in itself, but the gap list for anything TEST-04 and TEST-05 imply.

1. `gold-company-notes.sql`: the `yc_batch` to `'YC ' || yc_batch` conversion,
   and the invariant that exactly one of `notes`/`yc_batch` exists after the
   full ALTER set runs in filename order.
2. `gold-drop-icp-filter-pass.sql`, and the absence of `icp_filter_pass` from
   `gold.company`, `gold.company_history` and `TYPE_2_TRACKED_FIELDS`.
3. Eight further ALTER files with no execution coverage: `gold-company-scale`,
   `gold-company-stage`, `gold-company-status`, `gold-company-yc-batch`,
   `silver-yc-batch`, `silver-yc-former-names`, `silver-yc-industries-location`,
   `silver-yc-status-team-size`.
4. Every `_COMPANY_COLUMNS` name except `name` resolving to a real column.
5. An empty `industries` array reaching Gold. `company.py:208-212` writes
   `business_sector = []` because `[] is not None`, which on the last-non-null
   merge overwrites a known sector with an empty array. No test passes
   `industries=[]`, so neither that behaviour nor its opposite is pinned.
6. `_YC_STAGING_SELECT_SQL` column order against `_row_to_staged_signal`'s
   indices, statically.
7. A regression pointing the suite at a different real developer database.
8. Container teardown on SIGKILL; only testcontainers' reaper covers a hard
   kill and nothing asserts it.
9. A positive-path integration test for the history INSERT. Both
   `test_company_integration.py:74` and `:111` assert `history_count == 0`, so
   no test ever executes `_INSERT_HISTORY_SQL` on a real row.
10. `get_company`'s positional mapping, the statement change 2 shifted. The
    Gold *read* is guarded; `get_company` is not.
11. `team_composition_signal` in the history snapshot. Production is safe
    (`gold.company.team_composition_signal` is NOT NULL DEFAULT `'unknown'`),
    but the `FakeCompanyRepository` fixtures omit it and no assertion covers
    the snapshot's second field.

## Verified correct

Recorded so a fix does not disturb working parts.

- **Isolation is real.** No module under `tests/` reads `HUGINN_DATABASE_URL`.
  The only DSN literals are unreachable `example.invalid` hosts with
  monkeypatched connections. A full 332-test run left the dev database
  byte-identical: every table's row count, `gold.company.max(updated_at)`, and
  the server's database list all diffed empty.
- **Both tripwires genuinely fail on the original bug.** With a reverted
  conftest in a scratch tree, the behavioural test failed on matching identities
  and the static test named `conftest.py`.
- **Fixture lifetime holds.** Normal exit and a deliberate broken-schema run
  both leave no container. Under SIGINT the container was up at +2s and gone by
  +16s, reaped by testcontainers, with no leftovers.
- **No order dependence among tests.** All 12 integration files pass in
  isolation and in reverse file order; two consecutive full runs both give 332.
  Every whole-table operation filters its assertions by its own id or domain and
  cleans up in a `finally`.
- **Broken schema fails loudly.** Invalid SQL appended to a copy of `gold.sql`
  produced 5 errors and exit 1, not skips, and the pre-yield `container.stop()`
  still reaped the container.
- **CI works without `services.postgres`.** A faithful simulation with a bare
  environment, no `.env`, the variable unset, and a real `postgres:16-alpine`
  ran 331 passed. `ubuntu-latest` ships a working Docker daemon, `uv sync`
  installs the dev group, and `pgcrypto` is in the alpine image.
- **Positional index mapping.** `_GET_COMPANY_SQL` selects 4 columns and
  `get_company` maps 4; each index lands on its own key, verified with a
  distinct sentinel per column. `read_domain_normalized_signals` selects 8 and
  maps 8, likewise verified.
- **Placeholder and parameter parity.** `_INSERT_HISTORY_SQL` has 5 `%s` and
  `insert_history` binds 5; executed verbatim, 1 row written.
- **The allowlist cannot be bypassed.** A `not_a_real_column` key is dropped; a
  `domain` key in `new_values` does not reach SQL text or params, with
  `params[0]` staying the explicit argument. Filtering is on `_COMPANY_COLUMNS`
  membership, so no caller string reaches SQL text.
- **The notes merge.** Last-non-null; key omitted rather than blank when the
  batch is absent; format is exactly `"YC "` plus the source value.
- **Type 2 machinery end to end.** Driven through the real `write_company`,
  real upsert, real history INSERT: new domain with a sector writes 0 history
  rows; a real sector change on an existing row writes 1 carrying the
  superseded value with `valid_from < valid_to`; an identical re-run writes
  none.
- **Column-swaps and empty-array collapse are caught**, at both layers, by
  distinct-marker tests and by tests pinning `()` versus `NULL`.
- **The Acquired/Inactive filter is well guarded:** parser units for Acquired,
  Inactive, Public, Active and absent, the loader count test, and an end-to-end
  pass through the real loader.
- **The six YC fields work end to end.** A real bronze payload through the real
  loader, resolver and writer produced all seven derived Gold columns
  populated.
- **Ports and adapters, frozen dataclasses** intact in the Gold layer.
- **Fresh-install column parity is clean.** The full column set of the live
  migrated database was diffed against one built from the six base files alone:
  zero column, type or nullability differences.
- **Idempotency holds for all 12 files** under three consecutive individual
  re-applications to both a fresh install and a migrated database, and the full
  set applied six times alternating forward and reverse order.
- **`gold-company-signal-source-stable-id.sql` is correctly implemented.** All
  three documented states reproduce.
- **The ALTER inventory in `db/schema/README.md` is complete and correctly
  counted**: 12 files on disk, 12 table rows, exact filename match both ways.
- **`docs/entities.md:143-145`**, the paragraph about the lifecycle filter, is
  accurate: 4,349 of 6,252 staged, 1,903 skipped, gates-without-retracting
  stated correctly, and no Acquired or Inactive anywhere in Silver.
- **The Silver repository SQL is correct**: 14-column and 16-column inserts with
  matching placeholder counts, complete `ON CONFLICT SET` lists, and parameter
  tuples in the same order as the columns.

## Could not verify

- Whether Airbnb's founding date of August 2008 and the batch label `W09` are
  accurate. No founding date exists in YC's payload, and `W09` is not a value in
  this data; the row's `batch` is `Winter 2009`.
- The prior state of `icp_filter_pass` on the live database, since the column
  has been dropped and its state is unrecoverable.
- What the "6,204 live populated rows" and "6,298 domain_normalized" figures in
  SCHEMA-05 originally referred to; they are unreproducible now, which is not
  the same as knowing they were wrong when written.
- The origin of the `scratch_legacy` database on the dev server, nor the
  disappearance of `scratch_fresh`, `scratch_fwd` and `scratch_rev` between two
  review snapshots. All are activity from outside the suite under review.
- Two constraint names present in the live database but produced by no file in
  git history (`resolved_signals_source_key`, `manual_review_queue_signal_key`
  versus what a fresh `silver.sql` yields). They predate a commit that declared
  those constraints unnamed, and every `ON CONFLICT` in `src/` uses a column
  list, so nothing depends on them today.
- Runtime behaviour under concurrency. The `FOR UPDATE` claim at
  `company_repository.py:40-43` and `write_company`'s read-then-write were
  reasoned about, not exercised.
- Whether Docker Hub rate limiting actually triggers on GitHub runners for
  `postgres:16-alpine`. The mechanism in TEST-02 is verified; its frequency is
  not.
