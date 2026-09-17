# KAN-64: EU-Startups discovery adapter

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** A `WebScrapeSourcePort` ingestion adapter for eu-startups.com that
discovers new/updated startup listings via the site's XML sitemaps
(ADR-0008), fetches each one's detail page for the full field set, and a
Silver staging loader that turns Bronze rows into `EuStartupsListingStaging`
rows, mirroring `hn_staging.py`/`yc_staging.py`'s shape.

**Architecture:**
- `src/huginn/elt/ingestion/adapters/eu_startups.py`: sitemap discovery,
  detail-page parsing, `EuStartupsDiscoveryAdapter` (`WebScrapeSourcePort`).
- `src/huginn/elt/ingestion/ports.py`: add `DiscoveryWatermarkPort` (ADR-0009).
- `src/huginn/elt/silver/eu_startups_staging.py`: `parse_eu_startups_listing`,
  `EuStartupsStagingLoader`, mirroring `hn_staging.py`.
- `src/huginn/elt/silver/models.py`: add `EuStartupsListingStaging`.
- `src/huginn/elt/silver/ports.py`: add `EuStartupsStagingRepositoryPort`.

**Tech Stack:** Python 3.14, `requests` (already a dependency),
**`beautifulsoup4` (new dependency)** for detail-page field extraction, the
markup is a deterministic `div.wpbdp-field-value` structure (confirmed live,
see Global Constraint 2) that a plain regex would handle less robustly than
a real parser, and this codebase has no HTML parser yet since this is its
first scrape-based adapter. stdlib `xml.etree.ElementTree` for sitemap XML
(no new dependency needed, the sitemaps are well-formed with a standard
namespace). pytest, hand-rolled fixtures, no mocking framework.

**Spec:** Jira KAN-64 (fetch live for the authoritative text). ADR-0008
(sitemap-only discovery, not category-page pagination) and ADR-0009
(a new `DiscoveryWatermarkPort`, not extending `StatePort`), both already
written, read them in full, they are binding for this plan.
`docs/sources/eu-startups.md` (the underlying research). Real fixtures,
already captured live 2026-09-17, in `tests/fixtures/eu_startups/`:
`sitemap_index.xml`, `wpbdp_listing-sitemap165.xml`, `listing_brightroom.html`
(has every optional field), `listing_minut.html` (has none of the optional
fields, only the five always-present ones). `src/huginn/elt/ingestion/adapters/opencorporates.py`
and `src/huginn/elt/silver/hn_staging.py` (the sibling patterns this plan
mirrors throughout, read both before starting any task).

## Global Constraints

1. **Scope is sitemap-only discovery** (ADR-0008): no category-page
   pagination anywhere in this implementation. `fetch()` walks
   `sitemap_index.xml` -> every `wpbdp_listing-sitemap*.xml` file it lists ->
   every `(loc, lastmod)` pair in each -> for each one newer than the
   current watermark, fetch and parse its detail page.
2. **Detail-page field extraction, confirmed live structure.** Every field
   is `<div class="... wpbdp-field-value ... wpbdp-field-<slug> ...">`
   containing `<span class="field-label">Label</span>` and
   `<div class="value">...</div>`. Confirmed slugs from the real fixtures:
   `category` (value is an `<a>` tag, use its text), `business_description`,
   `long_business_description` (value contains a `<p>` wrapper, extract
   text), `based_in`, `tags`, `total_funding`, `founded`, `website`,
   `company_status`. Only `category`, `business_description`, `based_in`,
   `founded`, `website` are present on every listing (confirmed: both
   fixtures have exactly these five); every other slug is present on
   `listing_brightroom.html` and absent on `listing_minut.html`, treat all
   of them as optional, `None` when the `div.wpbdp-field-<slug>` element
   is not found, never an exception.
3. **Never construct a listing URL.** The only source of a listing URL is
   a sitemap `<loc>` entry. No `slugify(name)` anywhere in this codebase
   (`docs/sources/eu-startups.md`'s "URL construction" section: slugs
   collide and are not derivable).
4. **Watermark comparison is on `lastmod`, an ISO 8601 datetime string with
   a timezone offset** (confirmed in the fixtures, e.g.
   `2026-09-01T07:37:16+00:00`), parsed via `datetime.fromisoformat`
   (Python 3.14 parses this format natively, no external dependency).
   `DiscoveryWatermarkPort.read_watermark()` returning `None` means "no
   watermark yet, process every listing found" (first run).
   `save_watermark` is called once per `fetch()` call with the maximum
   `lastmod` seen across every listing actually processed this run, not
   called per-listing.
5. **`fetch_page(url) -> str`** is a plain `requests.get(url, headers=...)`
   with the confirmed-necessary browser `User-Agent`
   (`REACHABILITY_USER_AGENT`-equivalent, define a local constant, do not
   import from `huginn.elt.silver.resolution`, that constant is scoped to
   domain-reachability checks, this adapter's UA header is a separate,
   independent concern even though the literal string is the same one
   confirmed live in `docs/sources/eu-startups.md`), raising on a non-2xx
   response (matching `opencorporates.py`'s `try`/`except
   requests.RequestException` pattern, a sanitized custom exception for
   this adapter, not opencorporates.py's `OpenCorporatesRequestError`
   which is scoped to that adapter).
6. **Bronze stable_id**: the listing's slug extracted from its URL path
   (e.g. `https://www.eu-startups.com/directory/brightroom/` ->
   `"brightroom"`), not the full URL, matching this codebase's existing
   `stable_id` shape (a short identifier, not a URL, see
   `RawRecord.stable_id` usage in `opencorporates.py`/`hn.py`). The
   `RawRecord.payload` carries the full raw HTML string plus the listing
   URL, matching Bronze's raw-as-fetched contract (architecture document
   4.1): store what was fetched, no field mapping at this layer, the
   field extraction in Global Constraint 2 belongs to the Silver staging
   loader (Task 4), not the ingestion adapter (Task 3). The ingestion
   adapter's own `fetch()` does need to parse the sitemap XML to discover
   URLs and read `lastmod` (that is discovery, not field mapping of the
   listing's own business data), but must not extract Category/Website/etc.
   into the Bronze payload itself, that parsing happens once, in Task 4,
   against the raw HTML Bronze already stored.
7. **`mechanism = "web_scrape"`, `source = "eu_startups"`.**
8. **Bounded thread pool for the per-listing detail-page fetches**
   (ADR-0003), since a real run can process many listings in one `fetch()`
   call: `concurrent.futures.ThreadPoolExecutor`, a `max_workers` constructor
   parameter (default in the 5-10 range ADR-0003 already settled), matching
   `hn.py`'s existing use of the same pattern for concurrent fetches (read
   `hn.py`'s adapter for the exact usage before writing this one).
9. **Docstrings cite, don't restate** (`CLAUDE.md` code standard 3): ADR-0008,
   ADR-0009, Jira KAN-64, `docs/sources/eu-startups.md`, not restated
   reasoning.
10. **TDD, DB-free/network-free tests** (`CLAUDE.md` code standards 4, 5).
    Every test in this plan uses the real fixtures in
    `tests/fixtures/eu_startups/` or a hand-rolled fake, no `requests` call
    ever fires in a test, no test needs a database.
11. **Scope.** The Silver staging loader (Task 4) gets a Protocol
    (`EuStartupsStagingRepositoryPort`) and a model
    (`EuStartupsListingStaging`) but **no concrete Postgres repository
    implementation and no schema migration** in this plan: the ticket's own
    acceptance criteria only requires DB-free, fixture-based staging tests,
    and `CompanyWriter`/`CompanySignalWriter` (KAN-40/41) already establish
    the precedent of a Protocol with no orchestrator wiring yet. Building
    the concrete repository is real, separate follow-up work, file it as a
    KAN-16 debt ticket once this plan's tasks are done, don't build it here
    under time pressure.

---

## Task 1: Sitemap discovery + `DiscoveryWatermarkPort` + models

**Files:**
- Create: `src/huginn/elt/ingestion/adapters/eu_startups.py` (sitemap
  functions only in this task, the adapter class itself is Task 3)
- Modify: `src/huginn/elt/ingestion/ports.py` (add `DiscoveryWatermarkPort`)
- Test: `tests/elt/ingestion/test_eu_startups.py` (new file, sitemap-parsing
  tests only in this task)

**Interfaces:**
- Produces: `_parse_sitemap_index(xml_text: str) -> list[str]` (every
  `<loc>` inside the index whose URL contains `wpbdp_listing-sitemap`, in
  document order).
- Produces: `_parse_listing_sitemap(xml_text: str) -> list[tuple[str, datetime]]`
  (every `(loc, lastmod)` pair, `lastmod` parsed to a timezone-aware
  `datetime`).
- Produces: `DiscoveryWatermarkPort` (Protocol, in `ingestion/ports.py`):
  `read_watermark(self, source: str) -> str | None`,
  `save_watermark(self, source: str, value: str) -> None`. Takes `source`
  as a parameter (not scoped to one adapter instance) since this Protocol
  lives in the shared `ingestion/ports.py`, other future adapters may reuse
  it (ADR-0009 doesn't preclude that, it only decided not to overload
  `StatePort`).

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from huginn.elt.ingestion.adapters.eu_startups import (
    _parse_listing_sitemap,
    _parse_sitemap_index,
)

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"


def _read_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text()


def test_parse_sitemap_index_returns_only_wpbdp_listing_sitemaps():
    urls = _parse_sitemap_index(_read_fixture("sitemap_index.xml"))

    assert len(urls) == 165
    assert all("wpbdp_listing-sitemap" in url for url in urls)
    assert "https://www.eu-startups.com/wpbdp_listing-sitemap165.xml" in urls


def test_parse_sitemap_index_does_not_include_post_or_job_sitemaps():
    urls = _parse_sitemap_index(_read_fixture("sitemap_index.xml"))

    assert not any("post-sitemap" in url for url in urls)
    assert not any("job-sitemap" in url for url in urls)


def test_parse_listing_sitemap_returns_loc_and_lastmod_pairs():
    entries = _parse_listing_sitemap(_read_fixture("wpbdp_listing-sitemap165.xml"))

    assert len(entries) > 0
    first_url, first_lastmod = entries[0]
    assert first_url == "https://www.eu-startups.com/directory/brightroom/"
    assert first_lastmod == datetime(2026, 9, 1, 7, 37, 16, tzinfo=UTC)


def test_parse_listing_sitemap_every_entry_has_a_timezone_aware_lastmod():
    entries = _parse_listing_sitemap(_read_fixture("wpbdp_listing-sitemap165.xml"))

    assert all(lastmod.tzinfo is not None for _, lastmod in entries)
```

Run `uv run pytest tests/elt/ingestion/test_eu_startups.py -v`, confirm
every test fails (import error, nothing exists yet).

- [ ] **Step 2: Implement**

`src/huginn/elt/ingestion/ports.py`: add, after `NewsletterSourcePort`:

```python
class DiscoveryWatermarkPort(Protocol):
    """A single per-source "highest lastmod already processed" scalar, for
    a source whose discovery mechanism (a sitemap, an index feed) exposes
    a per-item timestamp usable as an incremental cursor. See ADR-0009 for
    why this is not folded into huginn.elt.bronze.ports.StatePort.
    """

    def read_watermark(self, source: str) -> str | None:
        """The stored watermark for `source`, or None if never set (a
        first run, process everything discovery finds).
        """
        ...

    def save_watermark(self, source: str, value: str) -> None:
        """Persist `value` as the new watermark for `source`."""
        ...
```

`src/huginn/elt/ingestion/adapters/eu_startups.py` (new file): module
docstring citing ADR-0008, ADR-0009, KAN-64, `docs/sources/eu-startups.md`.
Implement `_parse_sitemap_index` and `_parse_listing_sitemap` using
`xml.etree.ElementTree`, handling the sitemap namespace
(`{http://www.sitemaps.org/schemas/sitemap/0.9}`) explicitly (either via
the full namespaced tag string or `ElementTree`'s namespace-map argument to
`findall`, your call, whichever reads more clearly, both work against the
real fixture). `_parse_sitemap_index` filters to URLs containing
`"wpbdp_listing-sitemap"`. `_parse_listing_sitemap` parses each `<url>`'s
`<loc>` and `<lastmod>` (ignore `<image:image>`, not needed).

Run the tests again, confirm all pass. Run
`uv run ruff check . && uv run ruff format --check .`.

- [ ] **Step 3: Commit**

One commit, message describing what was added (KAN-64, ADR-0008/0009), no
Claude/Anthropic attribution.

---

## Task 2: Detail-page field extraction

**Depends on:** none (independent of Task 1, both feed Task 3).

**Files:**
- Modify: `src/huginn/elt/ingestion/adapters/eu_startups.py` (add the field
  extraction function)
- Modify: `pyproject.toml` (add `beautifulsoup4` to `dependencies`)
- Test: `tests/elt/ingestion/test_eu_startups.py` (add to the same file
  Task 1 created)

**Interfaces:**
- Produces: `extract_listing_fields(html_text: str) -> dict[str, str | None]`,
  a public function (Task 4's Silver staging loader calls this directly
  against the raw HTML Bronze stored, per Global Constraint 6). Keys:
  `"category"`, `"business_description"`, `"long_business_description"`,
  `"based_in"`, `"tags"`, `"total_funding"`, `"founded"`, `"website"`,
  `"company_status"`. Every key always present in the returned dict; value
  is `None` when that field's `div.wpbdp-field-<slug>` element is absent.

- [ ] **Step 1: Write the failing tests**

Add to `tests/elt/ingestion/test_eu_startups.py`:

```python
from huginn.elt.ingestion.adapters.eu_startups import extract_listing_fields


def test_extract_listing_fields_gets_every_field_when_all_present():
    fields = extract_listing_fields(_read_fixture("listing_brightroom.html"))

    assert fields["category"] == "Germany"
    assert "invite-only coaching marketplace" in fields["business_description"]
    assert fields["long_business_description"] is not None
    assert "curated, invite-only coaching marketplace" in fields["long_business_description"]
    assert fields["based_in"] == "Berlin"
    assert fields["tags"] == "coaching, marketplace, career development, professional development, invite-only"
    assert fields["total_funding"] == "No funding announced yet"
    assert fields["founded"] == "2024"
    assert fields["website"] == "https://thebrightroom.de"
    assert fields["company_status"] == "Active"


def test_extract_listing_fields_leaves_optional_fields_none_when_absent():
    fields = extract_listing_fields(_read_fixture("listing_minut.html"))

    assert fields["category"] == "Sweden"
    assert fields["based_in"] == "Malmo"
    assert fields["founded"] == "2014"
    assert fields["website"] == "https://minut.com/"
    assert fields["tags"] is None
    assert fields["total_funding"] is None
    assert fields["company_status"] is None
    assert fields["long_business_description"] is None


def test_extract_listing_fields_never_raises_on_a_field_free_fragment():
    """An empty or unrelated HTML document has no wpbdp-field elements at
    all; every key must still be present, all values None, no exception."""
    fields = extract_listing_fields("<html><body>not a listing</body></html>")

    assert fields["category"] is None
    assert fields["website"] is None
    assert set(fields.keys()) == {
        "category",
        "business_description",
        "long_business_description",
        "based_in",
        "tags",
        "total_funding",
        "founded",
        "website",
        "company_status",
    }
```

Run the tests, confirm they fail (function doesn't exist yet).

- [ ] **Step 2: Implement**

Add `beautifulsoup4` to `pyproject.toml`'s `dependencies` list, run `uv sync`
(or equivalent, whatever this project's normal dependency-install command
is, check `README.md` if unsure) so it is actually installed before running
tests.

Implement `extract_listing_fields` in `eu_startups.py` using
`BeautifulSoup(html_text, "html.parser")` (stdlib parser backend, no
`lxml` dependency needed). For each of the nine known slugs, find the
element via `soup.select_one(f"div.wpbdp-field-{slug} .value")` (confirmed
selector shape against the real fixtures, Global Constraint 2). If found,
extract `.get_text(strip=True)` for every field except `category` (its
value is inside an `<a>` tag, `.get_text(strip=True)` on the `.value` div
still gets the link's text correctly, BeautifulSoup's `get_text` descends
into children) and `long_business_description` (contains a `<p>`, strip
tags the same way via `.get_text(strip=True)`, whitespace-normalized is
fine, this field is prose, not structured data). If not found, `None`.

Run the tests again, confirm all pass. Run
`uv run ruff check . && uv run ruff format --check .`.

- [ ] **Step 3: Commit**

One commit, message describing what was added, citing that this adds
`beautifulsoup4` as a new dependency and why (first HTML-scraping adapter
in this codebase), no Claude/Anthropic attribution.

---

## Task 3: `EuStartupsDiscoveryAdapter`

**Depends on:** Task 1 (sitemap functions, `DiscoveryWatermarkPort`) and
Task 2 (`extract_listing_fields`... actually, per Global Constraint 6, the
adapter itself does NOT call `extract_listing_fields`, that belongs to
Task 4's Silver staging loader. Task 3 only needs Task 1's sitemap
functions.).

**Files:**
- Modify: `src/huginn/elt/ingestion/adapters/eu_startups.py` (add the
  adapter class)
- Test: `tests/elt/ingestion/test_eu_startups.py` (add to the same file)

**Interfaces:**
- Produces: `EuStartupsDiscoveryAdapter(watermark_port: DiscoveryWatermarkPort, timeout: float = 10.0, max_workers: int = 5)`
  implementing `WebScrapeSourcePort`: `source = "eu_startups"`,
  `mechanism = "web_scrape"`, `fetch_page(url: str) -> str`,
  `fetch(self) -> list[RawRecord]`.

- [ ] **Step 1: Write the failing tests**

```python
from huginn.elt.ingestion.adapters.eu_startups import EuStartupsDiscoveryAdapter


class FakeWatermarkPort:
    def __init__(self, watermark=None):
        self._watermark = watermark
        self.saved = []

    def read_watermark(self, source):
        return self._watermark

    def save_watermark(self, source, value):
        self.saved.append((source, value))


def test_fetch_processes_every_listing_when_no_watermark_yet(monkeypatch):
    adapter = EuStartupsDiscoveryAdapter(watermark_port=FakeWatermarkPort(watermark=None))
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: {
            "https://www.eu-startups.com/sitemap_index.xml": _read_fixture("sitemap_index.xml"),
        }.get(url, _read_fixture("wpbdp_listing-sitemap165.xml"))
        if "sitemap" in url
        else _read_fixture("listing_brightroom.html"),
    )

    records = adapter.fetch()

    assert len(records) > 0
    assert all(record.stable_id for record in records)


def test_fetch_skips_listings_at_or_before_the_watermark(monkeypatch):
    """A watermark equal to every fixture entry's lastmod means nothing
    new to process."""
    adapter = EuStartupsDiscoveryAdapter(
        watermark_port=FakeWatermarkPort(watermark="2026-09-09T15:04:00+00:00")
    )
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _read_fixture("sitemap_index.xml")
        if "sitemap_index" in url
        else _read_fixture("wpbdp_listing-sitemap165.xml"),
    )

    records = adapter.fetch()

    assert records == []


def test_fetch_saves_the_new_watermark_after_processing(monkeypatch):
    watermark_port = FakeWatermarkPort(watermark=None)
    adapter = EuStartupsDiscoveryAdapter(watermark_port=watermark_port)
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _read_fixture("sitemap_index.xml")
        if "sitemap_index" in url
        else (
            _read_fixture("wpbdp_listing-sitemap165.xml")
            if "wpbdp_listing" in url
            else _read_fixture("listing_brightroom.html")
        ),
    )

    adapter.fetch()

    assert len(watermark_port.saved) == 1
    saved_source, saved_value = watermark_port.saved[0]
    assert saved_source == "eu_startups"


def test_raw_record_stable_id_is_the_listing_slug_not_the_full_url(monkeypatch):
    adapter = EuStartupsDiscoveryAdapter(watermark_port=FakeWatermarkPort(watermark=None))
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _read_fixture("sitemap_index.xml")
        if "sitemap_index" in url
        else (
            _read_fixture("wpbdp_listing-sitemap165.xml")
            if "wpbdp_listing" in url
            else _read_fixture("listing_brightroom.html")
        ),
    )

    records = adapter.fetch()

    assert all("/" not in record.stable_id for record in records)
    assert all(not record.stable_id.startswith("http") for record in records)
```

Note: the plan's own test fixtures only cover file `wpbdp_listing-sitemap165.xml`
for every sitemap URL the adapter tries to fetch (the monkeypatch above
routes every `wpbdp_listing-sitemap*.xml` request to the same fixture file
regardless of which of the 165 URLs was requested), which means a real
`fetch()` run in this test set will process the same 87 listings' worth of
`(url, lastmod)` entries once per sitemap file the index lists (165 times).
This is fine for proving the logic under test (watermark filtering,
stable_id shape, save-once-at-the-end), but implementers should use a small
`max_workers`/expect this test to take a moment, not treat a slow test run
as a bug. If this turns out impractically slow, restrict the test's index
fixture to a hand-written 2-3-URL XML string instead of the full real one,
your call, whichever keeps the test fast without losing what it proves.

- [ ] **Step 2: Implement**

`EuStartupsDiscoveryAdapter.fetch_page(url)`: plain `requests.get(url,
headers={"User-Agent": <the confirmed UA string>}, timeout=self._timeout)`,
`response.raise_for_status()`, return `response.text`.

`EuStartupsDiscoveryAdapter.fetch()`:
1. `watermark = self._watermark_port.read_watermark("eu_startups")`, parse
   to `datetime` if not None (reuse the same `datetime.fromisoformat`
   approach as Task 1).
2. `sitemap_urls = _parse_sitemap_index(self.fetch_page(<sitemap index URL>))`.
3. For each sitemap URL, `entries = _parse_listing_sitemap(self.fetch_page(url))`.
4. Filter every `(loc, lastmod)` pair across all sitemap files to
   `lastmod > watermark` (or all of them if `watermark is None`).
5. For each surviving `(loc, lastmod)`, fetch its detail page HTML
   (`self.fetch_page(loc)`) using a bounded `ThreadPoolExecutor` (Global
   Constraint 8, mirror `hn.py`'s exact usage), extract the slug from
   `loc`'s path (`loc.rstrip("/").rsplit("/", 1)[-1]`), build one
   `RawRecord(stable_id=slug, payload={"url": loc, "html": html_text})`.
6. After processing, if any listing was processed, call
   `self._watermark_port.save_watermark("eu_startups", <max lastmod seen,
   as its original ISO string or re-serialized via .isoformat()>)`, once,
   not per-listing. If nothing was processed (nothing newer than the
   watermark), don't call `save_watermark` at all (no new maximum to
   record).

Hardcode the sitemap index URL as a module constant
(`"https://www.eu-startups.com/sitemap_index.xml"`).

Run the tests again, confirm all pass. Run `uv run pytest` (full suite),
`uv run ruff check . && uv run ruff format --check .`.

- [ ] **Step 3: Commit**

One commit, no Claude/Anthropic attribution.

---

## Task 4: Silver staging loader

**Depends on:** Task 2 (`extract_listing_fields`).

**Files:**
- Modify: `src/huginn/elt/silver/models.py` (add `EuStartupsListingStaging`)
- Modify: `src/huginn/elt/silver/ports.py` (add `EuStartupsStagingRepositoryPort`)
- Create: `src/huginn/elt/silver/eu_startups_staging.py`
- Test: `tests/elt/silver/test_eu_startups_staging.py` (new file)

**Interfaces:**
- Produces: `EuStartupsListingStaging` (frozen dataclass): `stable_id: str`,
  `company_name_raw: str`, `website: str | None`, `signal_type: str`,
  `stage: str | None`, `description: str`, `occurred_on: datetime`,
  `url: str` (matching `HnPostingStaging`'s exact shape, per this ticket's
  own Global Constraint that this mirrors the sibling staging models,
  even though a couple of these fields, `stage`/`occurred_on`, don't map
  naturally from a startup directory listing, see Step 2 for what to put
  there).
- Produces: `EuStartupsStagingRepositoryPort(BronzeReaderPort, Protocol)`
  in `silver/ports.py`: `def upsert(self, row: EuStartupsListingStaging) -> None: ...`
  (mirrors `HnStagingRepositoryPort` exactly).
- Produces: `parse_eu_startups_listing(payload: dict) -> EuStartupsListingStaging | None`,
  `EuStartupsStagingLoader(repository)` with `.load() -> int`.

- [ ] **Step 1: Write the failing tests**

Create `tests/elt/silver/test_eu_startups_staging.py`:

```python
from __future__ import annotations

from pathlib import Path

from huginn.elt.silver.eu_startups_staging import (
    EuStartupsStagingLoader,
    parse_eu_startups_listing,
)
from huginn.elt.silver.models import EuStartupsListingStaging

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"


def _payload(html_name: str, url: str) -> dict:
    return {"url": url, "html": (_FIXTURES / html_name).read_text()}


def test_parse_eu_startups_listing_maps_every_confirmed_field():
    row = parse_eu_startups_listing(
        _payload("listing_brightroom.html", "https://www.eu-startups.com/directory/brightroom/")
    )

    assert row is not None
    assert row.company_name_raw  # Business Description text, see Step 2
    assert row.website == "https://thebrightroom.de"
    assert row.url == "https://www.eu-startups.com/directory/brightroom/"


def test_parse_eu_startups_listing_handles_missing_optional_fields():
    row = parse_eu_startups_listing(
        _payload("listing_minut.html", "https://www.eu-startups.com/directory/minut/")
    )

    assert row is not None
    assert row.website == "https://minut.com/"


def test_parse_eu_startups_listing_returns_none_when_no_website_field_at_all():
    """A payload whose HTML has no wpbdp fields at all (a malformed or
    unexpected fetch) yields no staging row rather than a row full of
    None/empty values that would fail resolve_signal's own handling
    downstream."""
    row = parse_eu_startups_listing(
        {"url": "https://www.eu-startups.com/directory/broken/", "html": "<html></html>"}
    )

    assert row is None


class FakeEuStartupsStagingRepository:
    def __init__(self, bronze_rows):
        self._bronze_rows = bronze_rows
        self.upserted = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def read(self, source):
        return self._bronze_rows

    def upsert(self, row):
        self.upserted.append(row)


def test_loader_upserts_one_row_per_parseable_bronze_payload():
    repository = FakeEuStartupsStagingRepository(
        bronze_rows=[
            _payload("listing_brightroom.html", "https://www.eu-startups.com/directory/brightroom/"),
            _payload("listing_minut.html", "https://www.eu-startups.com/directory/minut/"),
        ]
    )
    loader = EuStartupsStagingLoader(repository)

    written = loader.load()

    assert written == 2
    assert len(repository.upserted) == 2
```

Run the tests, confirm they fail.

- [ ] **Step 2: Implement**

`src/huginn/elt/silver/models.py`: add `EuStartupsListingStaging`, same
field shape as `HnPostingStaging`. Field mapping from
`extract_listing_fields`'s dict:
- `company_name_raw`: this source has no separate "name" field on the
  listing page at all (confirmed, `docs/sources/eu-startups.md`'s field
  table has no "Name" row, the page's `<h1>`/title is the closest thing,
  but Bronze's stored payload here is `{"url": ..., "html": ...}`, no
  separately-captured title). Extract it from the HTML's `<title>` tag
  (confirmed present in every fixture, e.g. "Brightroom | EU-Startups"),
  splitting on `" | "` and taking the first segment. Add this extraction
  either inside `extract_listing_fields` (Task 2) as one more key, your
  call given you're the one implementing Task 4 after Task 2 already
  landed, whichever is less awkward to wire, but the tests above ask for
  it via `row.company_name_raw`, make sure it lands there one way or another.
- `website`: `fields["website"]`, as-is (KAN-62's `check_domain_reachable`
  and `resolve_signal`'s own `normalize_domain` handle a raw URL string
  fine, same as HN/YC already hand it a raw string).
- `signal_type`: always `"other"` (this source's schema constraint,
  `('hiring', 'funding', 'program_milestone', 'other')`, per
  `db/schema/silver.sql`, has no better fit for a directory listing that
  isn't itself a hiring post or a funding announcement).
- `stage`: `None`, this source has no funding-stage-shaped field (`Total
  Funding` is a free-text funding amount, not a stage enum, don't force
  a mapping that doesn't exist).
- `description`: `fields["business_description"]` (the short description,
  always present).
- `occurred_on`: the listing's sitemap `lastmod`, per Global Constraint 4
  of the ingestion plan; since this staging loader only has Bronze's
  stored payload (`{"url", "html"}`), not the sitemap lastmod directly,
  and adding it to the payload is a legitimate, small addition, revisit
  Task 3's `RawRecord.payload` shape and include the listing's `lastmod`
  there too (`{"url": ..., "html": ..., "lastmod": <isoformat string>}`),
  going back to amend Task 3's implementation if it already landed without
  this. Parse it here via `datetime.fromisoformat`.
- `url`: `payload["url"]`, as-is.
- `stable_id`: not part of `EuStartupsListingStaging` itself (matching
  `HnPostingStaging`, which also excludes it, the staging table's own
  Postgres schema would carry it as a separate column exactly like
  `hn_postings.stable_id` does, out of this plan's scope per Global
  Constraint 11, no schema/repository built here).

Return `None` if `fields["website"]` is `None` after extraction AND no
`title` tag was found (Global Constraint on "no fields at all" case), your
call on the exact guard condition as long as the third test above
(`test_parse_eu_startups_listing_returns_none_when_no_website_field_at_all`)
passes for the right reason (a genuinely empty/malformed page yields no
row) without also making the first two tests fail.

`src/huginn/elt/silver/eu_startups_staging.py`: mirror `hn_staging.py`'s
`EuStartupsStagingLoader` class shape exactly (`__init__(repository)`,
`load()` opens one `with self._repository:` scope, reads `read("eu_startups")`,
loops, upserts, logs, returns count).

Run the tests again, confirm all pass. Run `uv run pytest` (full suite),
`uv run ruff check . && uv run ruff format --check .`.

- [ ] **Step 3: File follow-up debt**

Use the Atlassian MCP tools to create one Task under Jira epic KAN-16:
"Build the Postgres repository and schema for silver.eu_startups_listings
and wire EuStartupsDiscoveryAdapter/EuStartupsStagingLoader into an
orchestrator", citing that Global Constraint 11 of this plan deferred it
deliberately, not by oversight. Do not build it in this task.

- [ ] **Step 4: Commit**

One commit, no Claude/Anthropic attribution.
