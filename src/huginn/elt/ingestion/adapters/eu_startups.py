"""EU-Startups discovery adapter. See architecture document section 5.

Discovery mechanism (sitemap-only, not category-page pagination): ADR-0008.
Incremental watermark (`DiscoveryWatermarkPort`, not `StatePort`): ADR-0009.
Research this adapter is built from: `docs/sources/eu-startups.md`. Ticket:
Jira KAN-64.

This module currently holds only the sitemap-parsing functions
(`_parse_sitemap_index`, `_parse_listing_sitemap`); detail-page field
extraction and the `WebScrapeSourcePort` adapter class land in later tasks
of the same plan.
"""

from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree

_SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP_URL_TAG = f"{{{_SITEMAP_NAMESPACE}}}url"
_SITEMAP_LOC_TAG = f"{{{_SITEMAP_NAMESPACE}}}loc"
_SITEMAP_LASTMOD_TAG = f"{{{_SITEMAP_NAMESPACE}}}lastmod"
_LISTING_SITEMAP_MARKER = "wpbdp_listing-sitemap"


def _parse_sitemap_index(xml_text: str) -> list[str]:
    """Every `<loc>` in a sitemap index whose URL is a listing sitemap
    (contains `wpbdp_listing-sitemap`), in document order. See ADR-0008:
    the index also lists post- and job-sitemaps, neither in this
    adapter's scope.
    """
    root = ElementTree.fromstring(xml_text)
    return [
        loc_element.text
        for loc_element in root.iter(_SITEMAP_LOC_TAG)
        if loc_element.text and _LISTING_SITEMAP_MARKER in loc_element.text
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
        entries.append((loc_element.text, datetime.fromisoformat(lastmod_element.text)))
    return entries
