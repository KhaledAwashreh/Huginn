# KAN-65: EU-Startups enrichment adapter (Advanced Search by business name)

Jira KAN-65. Branch `ingestion/kan-65-eu-startups-enrichment`, based on
`ingestion/kan-64-eu-startups-discovery` (a real dependency, but not a
code one: this adapter does not call KAN-64's `extract_listing_fields`,
see Global Constraint 10; the real dependency is that this ticket's tests
read fixture files KAN-64 added, `listing_brightroom.html` and
`listing_minut.html`). Spec authority: the KAN-65 Jira ticket text,
ADR-0010 (the blocking design decision the ticket itself flagged, resolved
before this plan was written).

## Context

KAN-65 adds a second EU-Startups ingestion adapter: given a company name,
search the site's Advanced Search, and if the search resolves to exactly
one company by that exact name, fetch its detail page and store it in
Bronze (mirroring `OpenCorporatesAdapter`'s "exactly one match enriches,
zero or many skips" pattern, KAN-53/54). Unlike OpenCorporates' API,
EU-Startups' search is a substring match, not exact: searching "Minut"
live-confirmed 9 results ("Minutemailer", "Feminutes", "3 Minutes Job",
etc. alongside the real "Minut"), so this adapter must filter the raw
search results to an exact name match itself before applying the
zero/one/many rule.

Real, live-captured evidence this plan is built from (fixtures added
2026-09-17, see `tests/fixtures/eu_startups/`):

- `search_brightroom.html`: searching "Brightroom" returns exactly 1
  result, named "Brightroom" (exact case match).
- `search_varm.html`: searching "Varm" returns exactly 1 result, named
  **"VARM"** — case differs from the query. The exact-match filter must be
  case-insensitive, or this real, legitimate single match would be
  wrongly treated as zero matches.
- `search_minut.html`: searching "Minut" returns 9 results; exactly one
  ("Minut") case-insensitively equals the query string.
- `search_zero_results.html`: a query with no matches; the page has no
  `.search-results` container at all.
- `listing_varm.html`, plus the existing `listing_brightroom.html` and
  `listing_minut.html` (KAN-64): detail pages for the positive-match cases.

## Global Constraints

1. **Reuse `extract_listing_fields` from KAN-64, don't duplicate it.**
   `from huginn.elt.ingestion.adapters.eu_startups import extract_listing_fields`.
   It is already built, tested, and reviewed (KAN-64); this ticket adds no
   new field-extraction logic. The one-line slug-from-url helper
   (`url.rstrip("/").rsplit("/", 1)[-1]`) is small enough that this
   codebase's own precedent (`eu_startups.py`'s `_listing_slug` and
   `eu_startups_staging.py`'s `_slug_from_url` are two independent copies
   of the same one-liner) is to duplicate it locally instead of importing
   a private (`_`-prefixed) helper across modules. Do the same here: a
   third private local copy, not an import.

2. **`source = "eu_startups"`, `mechanism = "web_scrape"`** (same as
   KAN-64's `EuStartupsDiscoveryAdapter`), so this adapter's Bronze rows
   land in the same `bronze.web_scrape_ingest` rows the existing
   `EuStartupsStagingLoader` (KAN-64) already reads, with zero new Silver
   code needed to pick up enrichment-discovered listings.
   **Ruling** (recorded here, not previously flagged by the ticket):
   `IngestionService`/`ops.job_runs` tracks run history keyed by
   `source.source` alone (`start_job_run(source.source)`,
   `service.py:62`), so discovery's and enrichment's job runs will be
   indistinguishable in `ops.job_runs` under this shared source name.
   Accepted as a minor, non-blocking observability tradeoff: extending
   `ops.job_runs`'s schema with a per-adapter-role dimension is out of
   this ticket's scope (its own scope text says "New ingestion adapter,
   enrichment-only," nothing about job-run tracking), and per-adapter
   detail is still visible in this adapter's own log lines
   (Constraint 8 below). If this tradeoff turns out to matter in
   practice, it is a small, independent follow-up, not a reason to block
   this ticket.

3. **This adapter's Bronze payload has no genuine source-reported
   `lastmod`** (unlike KAN-64's sitemap walk). Use the fetch's own
   timestamp, `datetime.now(UTC).isoformat()`, as `payload["lastmod"]`,
   captured once per successful enrichment, not recomputed between the
   payload's construction and any later read. **Ruling**: this is a
   documented approximation, not a real "site last modified this listing"
   fact; `eu_startups_staging.py`'s `occurred_on` will reflect "when this
   adapter last confirmed the listing," not the site's own edit time, for
   any row that reaches Silver via enrichment rather than discovery. How a
   discovery-sourced and an enrichment-sourced Bronze row for the same
   listing interact (which `lastmod` wins on a hash-compare, whether one
   should even overwrite the other) is deferred to KAN-83, the same
   ticket ADR-0009 already named for eu-startups' cross-adapter
   orchestration questions; neither adapter is wired into `__main__.py`
   yet; this ticket does not add that wiring either (not in KAN-65's
   scope text).

4. **Candidate names are injected exactly like `OpenCorporatesAdapter`**:
   `EuStartupsEnrichmentAdapter.__init__(self, company_loader:
   Callable[[], list[str]], max_calls: int, timeout: float = ...)`. The
   adapter does not query Gold itself; `company_loader` is called once,
   lazily, from inside `fetch()`. This ticket does not wire a real
   `company_loader` into `ingestion/__main__.py` (not in KAN-65's scope
   text, matching KAN-64's own precedent of leaving orchestrator wiring to
   a later ticket); only the Protocol method and its Postgres
   implementation are built (Task 1).

5. **New `EnrichmentCandidatePort` method** (per ADR-0010, resolving
   KAN-65's own blocking design decision): `read_company_names_pending_eu_startups_search(self, limit: int) -> list[str]`.
   Implementation and query mirror `read_unenriched_company_names`/
   `build_read_unenriched_company_names_query` exactly, with
   `eu_startups_searched_at IS NULL` in place of `business_sector IS NULL`.
   Per ADR-0010's Decision Outcome, nothing in this ticket's scope ever
   writes `eu_startups_searched_at`; only the column and the read are
   built here.

6. **Search request** (confirmed live against the real site,
   `listingfields[1]` is the Business Name field):
   `GET https://www.eu-startups.com/directory/?dosrch=1&q=&wpbdp_view=search&listingfields[1]=<url-encoded name>&listingfields[2]=-1&listingfields[7]=&listingfields[6]=&listingfields[4]=-1`.
   Build this URL with `urllib.parse.urlencode` (or `requests`' own
   `params=` dict, which handles encoding), never hand-built string
   concatenation. Use the exact same browser `User-Agent` string already
   confirmed live for this site (`_USER_AGENT` in
   `huginn/elt/ingestion/adapters/eu_startups.py`); duplicate the constant
   locally rather than importing a private name, same as Constraint 1.

7. **Result extraction**: `BeautifulSoup(html, "html.parser")
   .select(".search-results .listing-title a")` returns one `<a>` per
   result; `.get_text(strip=True)` is the displayed business name,
   `.get("href")` is the detail-page URL. A zero-result page has no
   `.search-results` container at all (confirmed live,
   `search_zero_results.html`), but `.select(...)` on such a page still
   returns `[]` with no special-casing needed.

8. **Exact-match filter, case-insensitive**: after extracting
   `(name, url)` pairs, keep only those where
   `name.strip().casefold() == query_name.strip().casefold()`. This is
   confirmed necessary by real data: "Varm" the query matches "VARM" the
   result, differing only in case. Apply this filter before the
   zero/one/many skip rule below, not after.

9. **Skip rule, mirroring `opencorporates.py`'s `fetch()` exactly**:
   after the exact-match filter, exactly one candidate enriches (fetch its
   detail page, build one `RawRecord`); zero or more than one logs one
   INFO line naming the query and the match count, and skips, no
   exception raised. A `RawRecord` whose `stable_id` (the detail-page
   slug) was already produced earlier in the same `fetch()` call is
   skipped the same way `opencorporates.py` skips a duplicate
   `stable_id` (an INFO log, not an error): two different query names in
   the same run resolving to the same listing is possible if Gold ever
   holds near-duplicate names for one real company.

10. **Detail-page fetch and Bronze payload**: on exactly one exact match,
    call `self.fetch_page(detail_url)` (same `fetch_page` also used for
    the search request itself, per `WebScrapeSourcePort`'s contract: one
    fetch primitive, adapter decides which URLs to call it on). Do not
    call `extract_listing_fields` inside this adapter (Global Constraint 6
    of the KAN-64 plan still applies: Bronze stores raw HTML only, field
    extraction is a Silver-layer concern, already the shape
    `EuStartupsStagingLoader` expects). `RawRecord` payload:
    `{"url": detail_url, "html": detail_html, "lastmod": <fetch-time
    isoformat, Constraint 3>}`, `stable_id` = the local slug-from-url
    helper (Constraint 1) applied to `detail_url`.

11. **Tests are DB-free, fixture-based** (CLAUDE.md standard 4), using the
    real fixtures listed in Context above plus the existing
    `listing_brightroom.html`/`listing_minut.html`. Follow KAN-64's test
    style exactly: `monkeypatch.setattr(adapter, "fetch_page",
    fake_fetch_page)`, a `fake_fetch_page(url)` closure dispatching on a
    substring of `url` to decide which fixture to return. One test needs
    a "search resolves to more than one exact match" case that no live
    query naturally produced; construct a small, hand-written HTML
    snippet reusing the real `.search-results .listing-title a` structure
    with two identical exact names, the same "synthetic minimal HTML for
    an edge case no real page shows" pattern already used in
    `test_eu_startups_staging.py`'s
    `test_parse_eu_startups_listing_returns_none_when_no_website_field_at_all`.

12. `uv run ruff check .` and `uv run ruff format --check .` must pass.
    TDD mandatory (CLAUDE.md standard 5): failing test first for every
    behavior below.

## Task 1: Gold candidate query for EU-Startups enrichment

Files: `db/schema/gold.sql`, `src/huginn/elt/gold/ports.py`,
`src/huginn/elt/gold/repositories/company_repository.py`,
`tests/elt/gold/test_company_repository.py`,
`tests/elt/gold/test_company_repository_integration.py`.

1. `db/schema/gold.sql`: add `eu_startups_searched_at TIMESTAMPTZ` (no
   `NOT NULL`, no default; NULL means never searched) to `gold.company`'s
   column list, alongside the existing `business_sector` column. Not
   Type-2 tracked, not added to `gold.company_history` (ADR-0010: pipeline
   metadata, not a company fact).

2. `gold/ports.py`'s `EnrichmentCandidatePort`: add
   `read_company_names_pending_eu_startups_search(self, limit: int) -> list[str]`,
   docstring citing ADR-0010 and mirroring
   `read_unenriched_company_names`'s docstring shape ("up to `limit`
   gold.company names with `eu_startups_searched_at IS NULL`, oldest
   `created_at` first").

3. `company_repository.py`: add
   `_READ_COMPANY_NAMES_PENDING_EU_STARTUPS_SEARCH_SQL` (copy
   `_READ_UNENRICHED_COMPANY_NAMES_SQL` verbatim, swap the `WHERE` clause
   to `eu_startups_searched_at IS NULL`), a
   `build_read_company_names_pending_eu_startups_search_query(limit)`
   function returning `(sql, (limit,))`, and
   `PostgresCompanyRepository.read_company_names_pending_eu_startups_search(self, limit)`
   implementing the new port method the same way
   `read_unenriched_company_names` does (execute, fetch, return the name
   column as a flat list).

4. `test_company_repository.py`: add
   `test_build_read_company_names_pending_eu_startups_search_query_binds_limit_as_a_parameter`,
   mirroring `test_build_read_unenriched_company_names_query_binds_limit_as_a_parameter`
   exactly (assert `params == (limit,)`, the limit value itself is not in
   the SQL text, `"gold.company"` and `"eu_startups_searched_at IS NULL"`
   and `"LIMIT %s"` are).

5. `test_company_repository_integration.py`: add
   `test_read_company_names_pending_eu_startups_search_returns_only_rows_with_null_column`,
   mirroring
   `test_read_unenriched_company_names_returns_only_rows_with_null_business_sector`
   exactly (two inserted companies, one with `eu_startups_searched_at` set
   to a timestamp, one left NULL; assert only the NULL one comes back).
   This integration test is skipped automatically when
   `HUGINN_DATABASE_URL` is unset, same as its sibling; do not attempt to
   stand up a database.

## Task 2: EuStartupsEnrichmentAdapter

Files: `src/huginn/elt/ingestion/adapters/eu_startups_enrichment.py` (new),
`tests/elt/ingestion/test_eu_startups_enrichment.py` (new).

1. Module docstring citing: architecture document section 5, ADR-0010
   (candidate gate), KAN-64's `eu_startups.py` (the reused
   `extract_listing_fields` and the site's confirmed Cloudflare/UA
   behavior), Jira KAN-65.

2. `_SEARCH_URL = "https://www.eu-startups.com/directory/"` and a
   `_build_search_url(name: str) -> str` (or inline `params=` dict passed
   directly to `requests.get`, whichever reads more clearly) implementing
   Global Constraint 6's exact parameter set.

3. `_extract_exact_matches(html: str, query_name: str) -> list[tuple[str, str]]`:
   pure function, Global Constraints 7 and 8. Returns `(name, url)` pairs
   whose name case-insensitively equals `query_name`, in document order.

4. `EuStartupsEnrichmentAdapter(WebScrapeSourcePort)`:
   - `source = "eu_startups"`, `mechanism = "web_scrape"` (Constraint 2).
   - `__init__(self, company_loader, max_calls, timeout=10.0)`
     (Constraint 4; mirror `OpenCorporatesAdapter.__init__`'s docstring
     shape explaining why the loader is injected and called lazily).
   - `fetch_page(self, url: str) -> str`: identical shape to
     `EuStartupsDiscoveryAdapter.fetch_page` (GET with the browser UA,
     `raise_for_status()`, wrap `requests.RequestException` in a local
     `EuStartupsEnrichmentFetchError`; do not import KAN-64's
     `EuStartupsFetchError`, a new adapter gets its own exception type,
     same as every other adapter in this codebase having its own).
   - `fetch(self) -> list[RawRecord]`: for each name in
     `self._company_loader()[: self._max_calls]`: build the search URL,
     `fetch_page` it, catch `EuStartupsEnrichmentFetchError` and skip with
     a WARNING log (a single failed search must not abort the whole
     batch, same reasoning as KAN-64's per-listing fetch isolation);
     extract exact matches; apply the skip rule (Constraint 9); on
     exactly one match, `fetch_page` its detail URL (catching the same
     exception the same way), build the `RawRecord` (Constraint 10), skip
     duplicate `stable_id`s within the run (Constraint 9).

5. Tests (Global Constraint 11), one behavior per test:
   - Exactly one exact match (Brightroom): returns one `RawRecord`,
     `stable_id == "brightroom"`, payload contains the detail HTML and a
     `lastmod` that parses as a valid ISO timestamp.
   - Exactly one exact match with a case-differing result name (Varm
     query, "VARM" result): still enriches (proves Constraint 8).
   - Substring collision resolving to exactly one exact match (Minut
     query, 9 raw results, one exact): enriches only "Minut", proves the
     filter runs before the skip rule, not after.
   - Zero results: returns no `RawRecord`, one INFO log line, no
     exception.
   - More than one exact match (synthetic HTML, Global Constraint 11):
     returns no `RawRecord` for that name, one INFO log line.
   - A search request itself failing (simulate via the fake `fetch_page`
     raising): that name is skipped, a WARNING is logged, other pending
     names in the same run still process normally.
   - Two different query names resolving to the same detail URL in one
     run: only one `RawRecord` is returned (duplicate `stable_id`
     dedup, Constraint 9).

## Final Review

Full per-task review discipline (implementer + task reviewer + fix loop
per task, per `superpowers:subagent-driven-development`'s default
process), not KAN-64's skip-per-task-review shortcut: that shortcut's own
final review concluded it was the wrong call for this codebase's pace.
Final whole-branch review on the most capable available model before this
branch is considered ready to push.
