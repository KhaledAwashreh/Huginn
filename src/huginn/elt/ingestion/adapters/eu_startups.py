"""EU-Startups discovery adapter. See architecture document section 5.

Discovery mechanism (sitemap-only, not category-page pagination): ADR-0008.
Incremental watermark (`DiscoveryWatermarkPort`, not `StatePort`): ADR-0009.
Research this adapter is built from: `docs/sources/eu-startups.md`. Ticket:
Jira KAN-64.

This module holds the sitemap-parsing functions (`_parse_sitemap_index`,
`_parse_listing_sitemap`), detail-page field extraction
(`extract_listing_fields`), and `EuStartupsDiscoveryAdapter`, the
`WebScrapeSourcePort` implementation. Per Global Constraint 6 of the KAN-64
plan, `EuStartupsDiscoveryAdapter.fetch()` stores only raw HTML in Bronze;
it does not call `extract_listing_fields` itself, that belongs to the
Silver staging loader.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import DiscoveryWatermarkPort, WebScrapeSourcePort

logger = logging.getLogger(__name__)

_SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP_URL_TAG = f"{{{_SITEMAP_NAMESPACE}}}url"
_SITEMAP_LOC_TAG = f"{{{_SITEMAP_NAMESPACE}}}loc"
_SITEMAP_LASTMOD_TAG = f"{{{_SITEMAP_NAMESPACE}}}lastmod"
_LISTING_SITEMAP_MARKER = "wpbdp_listing-sitemap"

_SITEMAP_INDEX_URL = "https://www.eu-startups.com/sitemap_index.xml"
_EXPECTED_SCHEME = "https"
_EXPECTED_HOST = "www.eu-startups.com"

# Confirmed live (docs/sources/eu-startups.md): a plain browser User-Agent
# clears the Cloudflare check for this source. Independent of, and not
# imported from, huginn.elt.silver.resolution.REACHABILITY_USER_AGENT,
# which is scoped to domain-reachability checks (Global Constraint 5).
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

_REQUEST_TIMEOUT_SECONDS = 10.0
_MAX_CONCURRENT_FETCHES = 5

# Confirmed live detail-page field slugs (KAN-64 plan, Global Constraint 2).
# `category`, `business_description`, `based_in`, `founded`, `website` are
# present on every listing; the rest are optional.
_LISTING_FIELD_SLUGS = (
    "category",
    "business_description",
    "long_business_description",
    "based_in",
    "tags",
    "total_funding",
    "founded",
    "website",
    "company_status",
)


def _is_trusted_source_url(url: str, path_pattern: str) -> bool:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == _EXPECTED_SCHEME
        and parsed.hostname == _EXPECTED_HOST
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and re.fullmatch(path_pattern, parsed.path) is not None
    )


def _is_listing_sitemap_url(url: str) -> bool:
    return _is_trusted_source_url(url, r"/wpbdp_listing-sitemap[^/]*\.xml")


def _decoded_listing_slug(path: str) -> str | None:
    match = re.fullmatch(r"/directory/([^/]+)/?", path)
    if match is None:
        return None
    encoded_slug = match.group(1)
    if re.search(r"%(?![0-9A-Fa-f]{2})", encoded_slug):
        return None
    try:
        slug = unquote(encoded_slug, encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    if slug in {".", ".."} or any(
        not (character.isalnum() or character in "-._~") for character in slug
    ):
        return None
    return slug


def _is_listing_detail_url(url: str) -> bool:
    return (
        _is_trusted_source_url(url, r"/directory/[^/]+/?")
        and _decoded_listing_slug(urlparse(url).path) is not None
    )


def _parse_sitemap_index(xml_text: str) -> list[str]:
    """Every trusted eu-startups.com listing-sitemap `<loc>` in document
    order. See ADR-0008: the index also lists post- and job-sitemaps,
    neither in this adapter's scope. Origin and path validation prevents
    sitemap-controlled URLs from turning later fetches into SSRF.
    """
    root = ElementTree.fromstring(xml_text)
    return [
        loc_element.text
        for loc_element in root.iter(_SITEMAP_LOC_TAG)
        if loc_element.text
        and _LISTING_SITEMAP_MARKER in loc_element.text
        and _is_listing_sitemap_url(loc_element.text)
    ]


def _parse_listing_sitemap(xml_text: str) -> list[tuple[str, datetime]]:
    """Every `(loc, lastmod)` pair in one listing sitemap file, `lastmod`
    parsed to a timezone-aware `datetime` (Global Constraint 4: the
    fixtures carry an ISO 8601 offset, `datetime.fromisoformat` parses it
    natively on Python 3.14). `<image:image>` entries are ignored, this
    adapter has no use for listing images.
    """
    root = ElementTree.fromstring(xml_text)
    entries = []
    for url_element in root.iter(_SITEMAP_URL_TAG):
        loc_element = url_element.find(_SITEMAP_LOC_TAG)
        lastmod_element = url_element.find(_SITEMAP_LASTMOD_TAG)
        if loc_element is None or lastmod_element is None:
            continue
        if not loc_element.text or not lastmod_element.text:
            continue
        if not _is_listing_detail_url(loc_element.text):
            continue
        try:
            lastmod = datetime.fromisoformat(lastmod_element.text)
        except ValueError:
            continue
        if lastmod.utcoffset() is None:
            continue
        entries.append((loc_element.text, lastmod))
    return entries


def extract_listing_fields(html_text: str) -> dict[str, str | None]:
    """Every confirmed field from a listing detail page (Global Constraint 2):
    `<div class="... wpbdp-field-value ... wpbdp-field-<slug> ...">` holding
    a `div.value`. Every key in `_LISTING_FIELD_SLUGS` is always present in
    the returned dict; `None` when that field's element is absent, never an
    exception (a source page missing an optional field is expected, not an
    error).
    """
    soup = BeautifulSoup(html_text, "html.parser")
    fields: dict[str, str | None] = {}
    for slug in _LISTING_FIELD_SLUGS:
        value_element = soup.select_one(f"div.wpbdp-field-{slug} .value")
        fields[slug] = value_element.get_text(strip=True) if value_element else None
    return fields


class EuStartupsFetchError(RuntimeError):
    """A sanitized EU-Startups page-fetch failure safe to log."""


def _listing_slug(url: str) -> str:
    """The listing's directory slug from its detail-page URL, e.g.
    `https://www.eu-startups.com/directory/brightroom/` -> `"brightroom"`.
    Used as `RawRecord.stable_id` (Global Constraint 6): a short identifier,
    not a URL.
    """
    slug = _decoded_listing_slug(urlparse(url).path)
    if slug is None:
        raise ValueError("invalid EU-Startups listing URL")
    return slug


class EuStartupsDiscoveryAdapter(WebScrapeSourcePort):
    """`WebScrapeSourcePort` for eu-startups.com. Discovery is sitemap-only
    (ADR-0008): walk `sitemap_index.xml`, every `wpbdp_listing-sitemap*.xml`
    it lists, every `(loc, lastmod)` pair in each, fetch and store the raw
    detail-page HTML for every listing newer than the current watermark
    (ADR-0009, `DiscoveryWatermarkPort`). See Jira KAN-64 and
    `docs/sources/eu-startups.md`.
    """

    source = "eu_startups"
    mechanism = "web_scrape"

    def __init__(
        self,
        watermark_port: DiscoveryWatermarkPort,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
        max_workers: int = _MAX_CONCURRENT_FETCHES,
    ) -> None:
        self._watermark_port = watermark_port
        self._timeout = timeout
        self._max_workers = max_workers

    def fetch_page(self, url: str) -> str:
        """GET `url` with the confirmed browser User-Agent, raising a
        sanitized `EuStartupsFetchError` on a non-2xx response or a request
        failure (Global Constraint 5, mirrors `opencorporates.py`'s
        `try`/`except requests.RequestException` pattern with its own
        exception type, scoped to this adapter). Redirect following is
        disabled and every 3xx response is rejected so a trusted sitemap
        URL cannot redirect the request to another origin.
        """
        try:
            response = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=self._timeout,
                allow_redirects=False,
            )
            if 300 <= response.status_code <= 399:
                raise EuStartupsFetchError(
                    "EU-Startups page fetch failed: unexpected redirect"
                )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            raise EuStartupsFetchError(
                f"EU-Startups page fetch failed: {type(exc).__name__}"
            ) from None

    def fetch(self) -> list[RawRecord]:
        """Walk every listing sitemap the index lists, fetch every listing
        newer than the current watermark, and save the new watermark once
        (Global Constraint 4), called at most once per run, never
        per-listing, and not called at all if there was nothing pending.

        The new watermark is not simply "the maximum `lastmod` among
        successful fetches": a listing with an earlier `lastmod` that fails
        while a later one succeeds must not be skipped forever (CodeRabbit
        finding, KAN-64). If any pending listing failed this run, the new
        watermark is pinned to just before the earliest failure
        (`min(failed lastmods) - 1 second`), so that failure (and anything
        with an equal `lastmod`) stays eligible for retry next run, since
        the filter below is `lastmod > watermark`. Only when nothing failed
        does the watermark advance to the maximum successful `lastmod`.

        A single listing's detail-page fetch failing (a permanently broken
        404/410 URL) is logged and skipped, not allowed to abort the whole
        run: the alternative is a run that discards every already-fetched
        page and never advances the watermark, forever, over one bad URL.
        An empty sitemap index, by contrast, is a genuine discovery failure
        (see `_parse_sitemap_index` call below), not a per-listing issue.
        """
        watermark_value = self._watermark_port.read_watermark(self.source)
        watermark = datetime.fromisoformat(watermark_value) if watermark_value else None

        sitemap_urls = _parse_sitemap_index(self.fetch_page(_SITEMAP_INDEX_URL))
        logger.info(
            "eu_startups fetch: %d listing sitemap files found", len(sitemap_urls)
        )
        if not sitemap_urls:
            logger.warning(
                "eu_startups fetch: sitemap index listed zero listing sitemaps, "
                'treating as a discovery failure, not "nothing new"'
            )
            raise EuStartupsFetchError(
                "sitemap index listed zero wpbdp_listing-sitemap entries"
            )

        entries: list[tuple[str, datetime]] = []
        for sitemap_url in sitemap_urls:
            entries.extend(_parse_listing_sitemap(self.fetch_page(sitemap_url)))

        pending = [
            (loc, lastmod)
            for loc, lastmod in entries
            if watermark is None or lastmod > watermark
        ]
        logger.info(
            "eu_startups fetch: %d of %d listings pending past the watermark",
            len(pending),
            len(entries),
        )
        if not pending:
            return []

        fetched: list[tuple[str, datetime, str]] = []
        failed_lastmods: list[datetime] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_entry = {
                executor.submit(self.fetch_page, loc): (loc, lastmod)
                for loc, lastmod in pending
            }
            for future in as_completed(future_to_entry):
                loc, lastmod = future_to_entry[future]
                try:
                    html_text = future.result()
                except EuStartupsFetchError:
                    logger.warning(
                        "eu_startups fetch: skipping listing, detail-page fetch "
                        "failed: %s",
                        loc,
                    )
                    failed_lastmods.append(lastmod)
                    continue
                fetched.append((loc, lastmod, html_text))

        records = [
            RawRecord(
                stable_id=_listing_slug(loc),
                payload={"url": loc, "html": html_text, "lastmod": lastmod.isoformat()},
            )
            for loc, lastmod, html_text in fetched
        ]

        # `pending` is non-empty here (checked above), so at least one of
        # `fetched`/`failed_lastmods` is non-empty too: every pending entry
        # either succeeded or failed. If anything failed, the new watermark
        # must sit strictly before the earliest failure so it stays eligible
        # for retry next run (filter above is `lastmod > watermark`); a
        # later success must not be allowed to skip an earlier failure
        # forever (CodeRabbit finding, KAN-64).
        if failed_lastmods:
            new_watermark = min(failed_lastmods) - timedelta(seconds=1)
        else:
            new_watermark = max(lastmod for _loc, lastmod, _html in fetched)

        self._watermark_port.save_watermark(self.source, new_watermark.isoformat())
        logger.info("eu_startups fetch: watermark saved: %s", new_watermark.isoformat())

        return records
