"""EU-Startups enrichment adapter. See architecture document section 5.

Enrichment-only, mirroring `opencorporates.py`'s "exactly one search result
enriches, zero or many skips" pattern: given a company name, search
EU-Startups' directory, and if the search resolves to exactly one company by
that exact name, fetch its detail page and store the raw HTML in Bronze.
Unlike OpenCorporates' API, EU-Startups' search is a substring match, so
`_extract_exact_matches` filters the raw results before the zero/one/many
skip rule applies. Candidate gate: ADR-0010 (`gold.company
.eu_startups_searched_at`, wired at the composition root, not read from
here). Reuses `extract_listing_fields` and the confirmed Cloudflare/UA
behavior from `eu_startups.py` (KAN-64); this module does not call
`extract_listing_fields` itself (Bronze stores raw HTML only, KAN-64 plan
Global Constraint 6). Jira KAN-65.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import WebScrapeSourcePort

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.eu-startups.com/directory/"
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


def _extract_exact_matches(html: str, query_name: str) -> list[tuple[str, str]]:
    """Every `(name, url)` pair from a directory search results page whose
    displayed name case-insensitively equals `query_name`, in document
    order (plan Global Constraints 7 and 8).

    EU-Startups' search is a substring match, not exact: a query can return
    several raw results sharing a substring (confirmed live, "Minut"
    returns 9 results, only one of which is the real "Minut"). This filter
    runs on every raw result before any zero/one/many skip decision is
    made, so a substring collision never masks a genuine unambiguous match.
    A zero-result page has no `.search-results` container at all, but
    `.select(...)` on it still returns `[]`, no special-casing needed.
    """
    soup = BeautifulSoup(html, "html.parser")
    query_folded = query_name.strip().casefold()
    matches = []
    for anchor in soup.select(".search-results .listing-title a"):
        name = anchor.get_text(strip=True)
        if name.casefold() == query_folded:
            matches.append((name, anchor.get("href")))
    return matches


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
        """
        try:
            response = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=self._timeout,
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

            matches = _extract_exact_matches(search_html, name)
            if len(matches) != 1:
                logger.info(
                    "eu_startups_enrichment fetch: skipping %r, %d exact "
                    "match(es) (need exactly 1 to enrich unambiguously)",
                    name,
                    len(matches),
                )
                continue

            _matched_name, detail_url = matches[0]
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

            stable_id = _listing_slug(detail_url)
            if stable_id in seen_stable_ids:
                logger.info(
                    "eu_startups_enrichment fetch: skipping %r, duplicate stable ID %r",
                    name,
                    stable_id,
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
