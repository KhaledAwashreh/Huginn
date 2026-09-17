"""EU-Startups enrichment adapter. See architecture document section 5.

Enrichment-only, mirroring `opencorporates.py`'s "exactly one search result
enriches, zero or many skips" pattern: given a company name, search
EU-Startups' directory, and if the search resolves to exactly one company by
that exact name, fetch its detail page and store the raw HTML in Bronze.
Unlike OpenCorporates' API, EU-Startups' search is a substring match, so
`_extract_exact_matches` filters the raw results before the zero/one/many
skip rule applies. Candidate gate: ADR-0010 (`gold.company
.eu_startups_searched_at`); not read from here, and wiring that read into
the composition root is outside this ticket's scope (see `__init__`).
Reuses the confirmed Cloudflare/UA behavior from `eu_startups.py`
(KAN-64); this module does not call that module's `extract_listing_fields`
(Bronze stores raw HTML only, KAN-64 plan Global Constraint 6, field
extraction is a Silver-layer concern). Jira KAN-65.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

import requests
from bs4 import BeautifulSoup

from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import WebScrapeSourcePort

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.eu-startups.com/directory/"
_EXPECTED_SCHEME = "https"
_EXPECTED_HOST = "www.eu-startups.com"
_REQUEST_TIMEOUT_SECONDS = 10.0

# Confirmed live (docs/sources/eu-startups.md, same as eu_startups.py's
# `_USER_AGENT`): a plain browser User-Agent clears the Cloudflare check for
# this site. Duplicated locally rather than imported, matching this plan's
# Global Constraint 6 (a new adapter gets its own copy of the shared,
# private constants it needs, same reasoning as Global Constraint 1).
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class EuStartupsEnrichmentFetchError(RuntimeError):
    """A sanitized EU-Startups page-fetch failure safe to log.

    A distinct type from `eu_startups.py`'s `EuStartupsFetchError`: every
    adapter in this codebase owns its own exception type (plan Global
    Constraint 6 note; `opencorporates.py`'s `OpenCorporatesRequestError` is
    the other precedent).
    """


def _listing_slug(url: str) -> str:
    """The listing's directory slug from its detail-page URL, e.g.
    `https://www.eu-startups.com/directory/brightroom/` -> `"brightroom"`.
    Used as `RawRecord.stable_id`. A third local copy of the same one-liner
    `eu_startups.py`'s `_listing_slug` and `eu_startups_staging.py`'s
    `_slug_from_url` already duplicate independently (plan Global
    Constraint 1: too small to be worth importing a private helper for).
    """
    return url.rstrip("/").rsplit("/", 1)[-1]


def _build_search_url(name: str) -> str:
    """The Advanced Search request URL for `name` (plan Global Constraint
    6, confirmed live against the real site; `listingfields[1]` is the
    Business Name field). Built with `urllib.parse.urlencode`, never
    hand-built string concatenation, so bracketed parameter names and the
    company name are correctly percent-encoded.
    """
    params = {
        "dosrch": "1",
        "q": "",
        "wpbdp_view": "search",
        "listingfields[1]": name,
        "listingfields[2]": "-1",
        "listingfields[7]": "",
        "listingfields[6]": "",
        "listingfields[4]": "-1",
    }
    return f"{_SEARCH_URL}?{urlencode(params)}"


def _extract_raw_matches(html: str) -> list[tuple[str, str]]:
    """Every raw `(name, url)` anchor pair from a directory search results
    page, in document order, before any exact-match filtering or
    truncation check runs (plan Global Constraint 7). A zero-result page
    has no `.search-results` container at all, but `.select(...)` on it
    still returns `[]`, no special-casing needed.

    Kept as its own step, not inlined into `_extract_exact_matches`, so
    both the exact-match filter and the truncation check
    (`_is_result_set_truncated`, final whole-branch review Fix 1) work
    from the same raw extraction and neither has to reparse the page.

    An anchor with no `href` (CodeRabbit finding, KAN-65) is dropped here
    rather than returned as a `(name, None)` pair: `_listing_slug` requires
    a real URL, and letting `None` reach it would raise an uncaught
    `AttributeError` out of `fetch()` instead of being handled as an
    ordinary skip.
    """
    soup = BeautifulSoup(html, "html.parser")
    return [
        (anchor.get_text(strip=True), href)
        for anchor in soup.select(".search-results .listing-title a")
        if (href := anchor.get("href"))
    ]


def _extract_exact_matches(html: str, query_name: str) -> list[tuple[str, str]]:
    """Every `(name, url)` pair from `_extract_raw_matches(html)` whose
    displayed name case-insensitively equals `query_name` (plan Global
    Constraints 7 and 8).

    EU-Startups' search is a substring match, not exact: a query can return
    several raw results sharing a substring (confirmed live, "Minut"
    returns 9 results, only one of which is the real "Minut"). This filter
    runs on every raw result before any zero/one/many skip decision is
    made, so a substring collision never masks a genuine unambiguous match.
    """
    query_folded = query_name.strip().casefold()
    return [
        (name, url)
        for name, url in _extract_raw_matches(html)
        if name.casefold() == query_folded
    ]


def _parsed_result_count(html: str) -> int | None:
    """The page-reported total from a search results page's own
    `<h3>Search Results (N)</h3>` heading, or `None` when that heading is
    missing or its count isn't a plain integer.

    Confirmed live in all 4 real fixtures under `tests/fixtures/eu_startups/`
    (search_minut.html: 9, search_brightroom.html: 1, search_varm.html: 1,
    search_zero_results.html: 0), each matching that page's own raw anchor
    count exactly. Used by `_is_result_set_truncated` to detect a possibly
    paginated results page before the exact-match filter runs (final
    whole-branch review Fix 1: full pagination-following is a separate,
    future ticket, this is truncation detection only).
    """
    soup = BeautifulSoup(html, "html.parser")
    for heading in soup.find_all("h3"):
        match = re.search(r"Search Results\s*\((\d+)\)", heading.get_text())
        if match:
            return int(match.group(1))
    return None


def _is_eu_startups_detail_url(url: str) -> bool:
    """True only for an absolute `https://www.eu-startups.com/...` URL
    (CodeRabbit finding, KAN-65, CWE-918 SSRF): `detail_url` comes from an
    anchor `href` on a page this adapter fetched, not from a value this
    adapter constructed itself (unlike `_build_search_url`'s output). WPBDP
    always renders that anchor as its own internal listing link today, but
    nothing enforces that at the HTTP layer, so this adapter must not trust
    it blindly before making a second outbound request to it.
    """
    parsed = urlparse(url)
    return parsed.scheme == _EXPECTED_SCHEME and parsed.hostname == _EXPECTED_HOST


def _is_result_set_truncated(raw_match_count: int, parsed_count: int | None) -> bool:
    """True when a search results page's own reported total doesn't equal
    the number of raw anchors actually extracted, or when that total
    couldn't be found/parsed at all: either way, a signal the fetched page
    may not be the complete, unpaginated result set.

    A distinct, separately-testable step (pure integers in, no HTML
    parsing here) so it is visibly a precondition to the exact-match
    filter, not folded invisibly into it (final whole-branch review
    Fix 1).
    """
    return parsed_count is None or parsed_count != raw_match_count


class EuStartupsEnrichmentAdapter(WebScrapeSourcePort):
    """`WebScrapeSourcePort` for eu-startups.com, enrichment by company
    name. See Jira KAN-65 and ADR-0010.
    """

    source = "eu_startups"
    mechanism = "web_scrape"

    def __init__(
        self,
        company_loader: Callable[[], list[str]],
        max_calls: int,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """`company_loader` supplies the company names to search at fetch
        time, mirroring `opencorporates.py`'s `OpenCorporatesAdapter
        .__init__`.

        The adapter does not decide which companies to enrich; the loader
        is injected by `src/huginn/elt/ingestion/__main__.py` (ADR-0010's
        `read_company_names_pending_eu_startups_search`, wired outside this
        ticket's scope). Deferring the call until `fetch()` keeps service
        construction free of database I/O. `max_calls` caps how many
        searches this fetch makes, the same simple per-run budget
        `OpenCorporatesAdapter` uses.
        """
        self._company_loader = company_loader
        self._max_calls = max_calls
        self._timeout = timeout

    def fetch_page(self, url: str) -> str:
        """GET `url` with the confirmed browser User-Agent, raising a
        sanitized `EuStartupsEnrichmentFetchError` on a non-2xx response or
        a request failure. Identical shape to
        `eu_startups.py`'s `EuStartupsDiscoveryAdapter.fetch_page`, its own
        exception type per this module's docstring.

        `allow_redirects=False` (CodeRabbit finding, KAN-65, CWE-918 SSRF):
        `requests.get` follows redirects by default, which would let a
        same-origin URL that passed `_is_eu_startups_detail_url` still end
        up fetching an off-origin destination via a redirect hop. Mirrors
        `silver/resolution.py`'s `_request_with_retry`, this codebase's
        existing precedent for the same defense. A redirect response
        (3xx) is treated as a failure here, the same as a 4xx/5xx: unlike
        `_request_with_retry`'s own reachability check (which only needs to
        know a domain answers at all), this method needs the page's actual
        content, and a redirect's own short response body is never that.
        """
        try:
            response = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=self._timeout,
                allow_redirects=False,
            )
            if response.is_redirect:
                raise EuStartupsEnrichmentFetchError(
                    "EU-Startups page fetch failed: unexpected redirect"
                )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            raise EuStartupsEnrichmentFetchError(
                f"EU-Startups page fetch failed: {type(exc).__name__}"
            ) from None

    def fetch(self) -> list[RawRecord]:
        """Search for each company name in turn, up to `max_calls`
        searches, and enrich exactly the ones with an unambiguous exact
        match.

        Mirrors `opencorporates.py`'s `OpenCorporatesAdapter.fetch()`: a
        search resolving to exactly one exact-match result (plan Global
        Constraints 7-8) enriches that company (one `RawRecord`, plan
        Global Constraint 10). Zero or more than one exact match skips it
        this run, no guess, just an INFO log naming why. A single failed
        search (network error, non-2xx) is a WARNING, not an abort: it must
        not prevent the rest of the batch from being tried (same reasoning
        as KAN-64's per-listing fetch isolation).

        Before the exact-match filter runs, `_is_result_set_truncated`
        checks the page's own reported result count against the raw anchor
        count: WPBDP search pages paginate, and one fetched page is not on
        its own verified to be the complete result set. A mismatch (or a
        missing/unparsable count) is a WARNING, skip, same as any other
        unresolvable search this run (final whole-branch review Fix 1;
        following pagination is out of this ticket's scope).
        """
        records = []
        seen_stable_ids = set()
        for name in self._company_loader()[: self._max_calls]:
            try:
                search_html = self.fetch_page(_build_search_url(name))
            except EuStartupsEnrichmentFetchError:
                logger.warning(
                    "eu_startups_enrichment fetch: skipping %r, search request failed",
                    name,
                )
                continue

            raw_matches = _extract_raw_matches(search_html)
            parsed_count = _parsed_result_count(search_html)
            if _is_result_set_truncated(len(raw_matches), parsed_count):
                logger.warning(
                    "eu_startups_enrichment fetch: skipping %r, search results "
                    "page may be truncated (raw anchor count=%d, page-reported "
                    "count=%s)",
                    name,
                    len(raw_matches),
                    parsed_count if parsed_count is not None else "not found",
                )
                continue

            matches = _extract_exact_matches(search_html, name)
            if len(matches) != 1:
                logger.info(
                    "eu_startups_enrichment fetch: skipping %r, %d exact "
                    "match(es) out of %d raw search result(s) (need exactly 1 "
                    "exact match to enrich unambiguously)",
                    name,
                    len(matches),
                    len(raw_matches),
                )
                continue

            _matched_name, detail_url = matches[0]
            if not _is_eu_startups_detail_url(detail_url):
                logger.warning(
                    "eu_startups_enrichment fetch: skipping %r, detail URL is "
                    "not an eu-startups.com HTTPS URL: %s",
                    name,
                    detail_url,
                )
                continue

            stable_id = _listing_slug(detail_url)
            if stable_id in seen_stable_ids:
                logger.info(
                    "eu_startups_enrichment fetch: skipping %r, duplicate stable ID %r",
                    name,
                    stable_id,
                )
                continue

            try:
                detail_html = self.fetch_page(detail_url)
            except EuStartupsEnrichmentFetchError:
                logger.warning(
                    "eu_startups_enrichment fetch: skipping %r, detail page "
                    "fetch failed: %s",
                    name,
                    detail_url,
                )
                continue

            seen_stable_ids.add(stable_id)
            records.append(
                RawRecord(
                    stable_id=stable_id,
                    payload={
                        "url": detail_url,
                        "html": detail_html,
                        "lastmod": datetime.now(UTC).isoformat(),
                    },
                )
            )
        return records
