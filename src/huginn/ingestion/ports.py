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


class RawStorePort(Protocol):
    """Writes fetched records to Bronze. See architecture document section 4.1
    for the mechanism-grouped table layout and the hash-based write behavior.
    """

    def write(
        self, source: str, mechanism: str, records: list[RawRecord], run_id: str
    ) -> int:
        """Write records to the appropriate Bronze table, returning the
        count actually written (inserted or overwritten), excluding
        hash-match skips. `IngestionService` records this count on
        `ops.job_runs.rows_written`; it must not be `len(records)`, since a
        fully-static source correctly writes zero rows every run.

        Implementations must apply the skip-on-hash-match behavior: a
        record whose content hash matches the last stored hash for its
        `(source, stable_id)` should not insert a new row, only bump
        `last_checked_at` on the existing one. A record whose hash differs
        overwrites the existing row in place (Bronze's
        `UNIQUE (source, stable_id)` constraint allows exactly one row per
        entity; no prior version is retained).
        """
        ...


class StatePort(Protocol):
    """Per-entity content-hash watermark, replacing a source-provided cursor.
    See architecture document section 4.1: neither HN's Firebase API nor
    YC's Algolia backend offers a reliable "give me only what changed" cursor.
    """

    def last_hash(self, source: str, stable_id: str) -> str | None:
        """The last stored content hash for this entity, or None if never seen."""
        ...
