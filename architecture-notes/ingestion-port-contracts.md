# Ingestion Port Contracts (KAN-37)

Interface-contract note for KAN-26 (split `SourcePort` into mechanism-specific port abstractions). KAN-26 implements against the Protocol definitions below rather than inventing the contract inline.

Conclusion: keep a slimmed `SourcePort` base Protocol (`source`, `mechanism`, `fetch()`, unchanged in shape from the current one) and add three Protocols that extend it, one per Bronze mechanism table: `ApiSourcePort`, `WebScrapeSourcePort`, `NewsletterSourcePort`. `ApiSourcePort` adds nothing beyond the base. `WebScrapeSourcePort` and `NewsletterSourcePort` each add exactly one raw-content-fetch method the API case doesn't need, because an API response is already the structured shape `fetch()` wants and a scraped page or newsletter issue isn't.

## Contract

```python
"""Port contracts for ingestion. See architecture document section 5.

The core (`IngestionService`) depends on `SourcePort` and holds a single
`list[SourcePort]` mixing sources across mechanisms (see `service.py`).
Adapters implement one mechanism-specific port per source: HN and YC
implement `ApiSourcePort`; later sources implement `WebScrapeSourcePort`
or `NewsletterSourcePort`. Outbound concerns (writing to Bronze, tracking
cursor/watermark state) are their own ports so the core never depends on
Postgres directly.

Three sub-protocols exist, one per Bronze mechanism table (architecture
document section 4.1): `bronze.api_ingest`, `bronze.web_scrape_ingest`,
`bronze.newsletter_ingest`. Each shares `SourcePort`'s shape and adds the
one raw-content-fetch method its mechanism actually needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RawRecord:
    """One fetched record, prior to any Bronze-side hashing or storage.

    `stable_id` is the source-native identifier used for the
    `(source, stable_id)` uniqueness key at Bronze (see architecture
    document section 4.1). `payload` is the raw, unmodified data as
    fetched, stored as-is in Bronze's `payload` column.
    """

    stable_id: str
    payload: dict


class SourcePort(Protocol):
    """Common shape every source port has, regardless of mechanism.

    `IngestionService` calls `.fetch()`, `.source`, and `.mechanism` on
    every configured source uniformly; it does not need to know which
    mechanism-specific port a given adapter actually implements. Adapters
    implement one of `ApiSourcePort`, `WebScrapeSourcePort`, or
    `NewsletterSourcePort` below, never this protocol directly.
    """

    source: str
    """Short source identifier stored in Bronze's `source` column, e.g. "hn" or "yc"."""

    mechanism: str
    """Which Bronze table this source's rows land in: "api", "web_scrape", or "newsletter"."""

    def fetch(self) -> list[RawRecord]:
        """Fetch current records from the source. No ingestion policy here:
        pagination, retry, and rate-limit handling belong to the adapter,
        but *what to do* with the results (dedup, scheduling) is the
        `IngestionService`'s job, not this method's.
        """
        ...


class ApiSourcePort(SourcePort, Protocol):
    """Implemented once per source whose data comes from a structured API
    or API-shaped backend: an official JSON API (HN's Firebase API) or a
    directly-queried structured backend (YC's Algolia search-only key).
    `mechanism` is always "api" for implementations of this port. See
    architecture document section 5. Bronze destination:
    `bronze.api_ingest` (section 4.1).

    No method beyond `fetch()`. An API response is already the structured
    shape `fetch()` needs, so there is no separate raw-content step worth
    exposing at the port boundary here, unlike `WebScrapeSourcePort` and
    `NewsletterSourcePort` below. This is deliberately not a bare alias for
    `SourcePort`: a future API-only need (an auth-header method, a
    rate-limit attribute) has a home on this port without forcing
    `WebScrapeSourcePort` or `NewsletterSourcePort` to carry it too.
    """


class WebScrapeSourcePort(SourcePort, Protocol):
    """Implemented once per source whose data is extracted from rendered
    HTML with no structured API underneath (the VC-board, Ramp, and
    Harmonic candidates named in the concept doc, section 7). `mechanism`
    is always "web_scrape" for implementations of this port. See
    architecture document section 5. Bronze destination:
    `bronze.web_scrape_ingest` (section 4.1).
    """

    def fetch_page(self, url: str) -> str:
        """Fetch one page's rendered content and return it as HTML.
        Separated from `fetch()` so a slow or failed network call and the
        parsing logic that turns HTML into `RawRecord`s are independently
        testable: a parsing bug should be reproducible from a saved HTML
        fixture without re-fetching a live page, and a fetch failure should
        be retriable without re-running extraction.
        """
        ...

    def fetch(self) -> list[RawRecord]:
        """Fetch and parse current records from the source. Calls
        `fetch_page` for whichever URLs the source needs (a listing page,
        per-listing detail pages, or however the source's pagination is
        shaped) and extracts `RawRecord`s from the returned HTML. Which
        URLs to fetch and how to paginate is adapter-specific and not part
        of this contract: sites differ too much in structure to standardize
        past "you get a per-page fetch primitive."
        """
        ...


class NewsletterSourcePort(SourcePort, Protocol):
    """Implemented once per source whose data arrives as periodic
    newsletter issues (the four Substack feeds named in the concept doc,
    section 7). `mechanism` is always "newsletter" for implementations of
    this port. See architecture document section 5. Bronze destination:
    `bronze.newsletter_ingest` (section 4.1).
    """

    def fetch_issue(self, url: str) -> str:
        """Fetch one newsletter issue's raw content by its feed-provided
        URL or GUID (an RSS/Atom item's `<link>` or `<guid>`). Returns the
        issue body as delivered by the source: HTML for the Substack feeds,
        since Substack's RSS exposes issue content as HTML in
        `<content:encoded>`. Separated from `fetch()` for the same reason
        as `WebScrapeSourcePort.fetch_page`: a slow or failed fetch and a
        parsing bug should be independently reproducible and retriable.
        """
        ...

    def fetch(self) -> list[RawRecord]:
        """Fetch current issues and extract one `RawRecord` per company
        signal found inside each issue's content. Not a 1:1 issue-to-record
        mapping: a single issue routinely mentions more than one company.
        Issue discovery (which issue URLs currently exist, via the feed's
        own index) and the per-issue call to `fetch_issue` both happen
        here; no ingestion policy beyond that, same as the other two ports.
        """
        ...
```

## Shared versus mechanism-specific

1. Shared, on `SourcePort`, inherited by all three: `source: str`, `mechanism: str`, `fetch() -> list[RawRecord]`. This is what `IngestionService` actually depends on today (`service.py` holds `list[SourcePort]` and calls `.fetch()`, `.source`, `.mechanism` without branching on mechanism), so the base has to keep existing in some form even after the split, not just get deleted in favor of three unrelated Protocols.
2. Mechanism-specific:
   - `ApiSourcePort`: nothing added. A JSON API call, or a direct structured-backend query like YC's Algolia key, already returns the shape `fetch()` needs. HN and YC both implement this port and neither needs a new method.
   - `WebScrapeSourcePort`: adds `fetch_page(url: str) -> str`. Scraping needs an explicit raw-HTML-fetch step because the network call and the HTML-parsing logic are two different failure modes and should be two different test surfaces.
   - `NewsletterSourcePort`: adds `fetch_issue(url: str) -> str`, same shape and same reasoning as `fetch_page`, applied to a newsletter issue instead of a page.
3. Both mechanism-specific raw-fetch methods return `str` (raw content) rather than something more structured, because what counts as "structured" is source-specific past that point (a scraped page's DOM structure, an issue's HTML body) and standardizing further would mean guessing at a shape neither adapter exists yet to validate.
4. `fetch()` keeps the same signature and return type on all three ports. `IngestionService.run_once` (`service.py`) does not change: it still calls `source.fetch()`, `source.source`, `source.mechanism` on a mixed list without knowing which mechanism-specific port a given adapter implements.

## Why split at the port level

The reasoning is the one already used for splitting Silver into per-source staging tables rather than one shared table with a `Source` column (ADR-0001), applied one layer over: a single `SourcePort` carrying `fetch_page` and `fetch_issue` as optional methods (`None` when not applicable, or silently absent) means every call site that wants to use them needs a runtime `hasattr`/`isinstance` check to stay safe, and a bug that calls a scrape-only method on an API adapter fails at call time instead of being caught by the type checker before the adapter ever runs. That is the same shape of problem ADR-0001 names for a shared Silver table: a missing `WHERE Source = ...` filter is a runtime mistake with no structural barrier stopping it, where a per-source table makes the mistake impossible to make. Splitting the port per mechanism moves "does this adapter support scraping a page" from a runtime maybe to a static fact the type checker enforces, and lets a mechanism-specific need (a future `WebScrapeSourcePort.render_with_js(url: str) -> str` for a JS-heavy target, say) get added to just that port without forcing `ApiSourcePort` and `NewsletterSourcePort` to carry a method that means nothing for them. This mirrors ADR-0001's driver 3 (a source-specific need shouldn't force a schema change touching every other source) and its point against Option 2 (a source-specific column has no clean home without becoming a nullable field that means nothing for everyone else), with "column" replaced by "method" and "source" replaced by "mechanism."

## Judgment calls made here, flag before KAN-26 builds against this

1. **Confirmed by the user (2026-09-08): keep a shared `SourcePort` base Protocol**, not three fully independent Protocols. This is load-bearing: `IngestionService` (`src/huginn/ingestion/service.py`) currently types `sources` as `list[SourcePort]` and calls `.fetch()`/`.source`/`.mechanism` on a mixed-mechanism list without branching. Three unrelated Protocols with no common parent would force `service.py` into a union type or a runtime mechanism check it doesn't need today. KAN-26 builds against this decision as settled, not as an open question.
2. Did not narrow `mechanism` to a `Literal["api"]` / `Literal["web_scrape"]` / `Literal["newsletter"]` per port, even though that would let the type checker catch a misassigned mechanism string. Left as plain `str` on the base and documented instead, because overriding an inherited Protocol attribute's type with a narrower `Literal` has real potential for a type-checker variance complaint (attribute overrides are typically invariant) that I have not verified against this repo's mypy/pyright configuration. Worth a quick check during KAN-26 rather than assumed here.
3. `NewsletterSourcePort` has no existing adapter to validate against (unlike `ApiSourcePort`, checked against `hn.py` and `yc.py`). `fetch_issue(url: str) -> str` and the issue-discovery-happens-inside-`fetch()` design are a reasonable guess at the shape RSS/Substack-style ingestion needs, not something confirmed against a real newsletter source's API the way HN and YC were. Flag as the least-validated part of this note.
4. Did not add a `fetch_page`/`fetch_issue`-equivalent "discovery" method (a `list_pages()` or `list_issues()` primitive returning the URLs currently available) to either mechanism-specific port. Judgment call: discovery is left as adapter-internal logic inside `fetch()`, since a listing page's pagination shape and an RSS feed's own ordering differ too much per source to standardize now, with only zero adapters built against either mechanism yet. If KAN-26 or a later source adapter finds discovery genuinely shared across scrape/newsletter sources, that's a reason to add it then, not a reason it's missing now.

## Reference

`src/huginn/ingestion/ports.py` (current single-port version this note replaces). `src/huginn/ingestion/service.py` (the concrete usage this note's base-Protocol call is checked against). `src/huginn/ingestion/adapters/hn.py`, `yc.py` (both `ApiSourcePort` implementations checked against this contract). `docs/architecture.md` sections 4.1 and 5. `adr/0001-per-source-silver-staging-tables.md` (source of the blast-radius/independent-evolution reasoning adapted above). `architecture-notes/kan-21-build-plan.md` (KAN-37 blocks KAN-26).
