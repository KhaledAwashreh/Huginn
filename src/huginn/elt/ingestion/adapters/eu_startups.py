"""EU-Startups discovery adapter. See architecture document section 5.

Discovery mechanism (sitemap-only, not category-page pagination): ADR-0008.
Incremental watermark (`DiscoveryWatermarkPort`, not `StatePort`): ADR-0009.
Research this adapter is built from: `docs/sources/eu-startups.md`. Ticket:
Jira KAN-64.

This module currently holds the sitemap-parsing functions
(`_parse_sitemap_index`, `_parse_listing_sitemap`) and detail-page field
extraction (`extract_listing_fields`); the `WebScrapeSourcePort` adapter
class lands in a later task of the same plan.
"""

from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree

from bs4 import BeautifulSoup

_SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP_URL_TAG = f"{{{_SITEMAP_NAMESPACE}}}url"
_SITEMAP_LOC_TAG = f"{{{_SITEMAP_NAMESPACE}}}loc"
_SITEMAP_LASTMOD_TAG = f"{{{_SITEMAP_NAMESPACE}}}lastmod"
_LISTING_SITEMAP_MARKER = "wpbdp_listing-sitemap"

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
