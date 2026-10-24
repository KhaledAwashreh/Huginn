"""Deterministic extraction of source context from EU-Startups listings."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from huginn.elt.silver.models.source_extraction import SourceExtraction
from huginn.elt.silver.normalizers.eu_startups_url import _slug_from_url

_FIELD_SELECTORS = {
    "short_description": "business_description",
    "long_description": "long_business_description",
    "category": "category",
    "place": "based_in",
    "tags": "tags",
    "founded": "founded",
    "funding": "total_funding",
    "status": "company_status",
}


def _text(element: Tag | None) -> str | None:
    if element is None:
        return None
    for unwanted in element.select("script, style, noscript"):
        unwanted.decompose()
    value = re.sub(r"\s+([,.;:!?])", r"\1", " ".join(element.stripped_strings))
    return value or None


def _failed(
    stable_id: str | None, reason: str, source_url: str | None = None
) -> SourceExtraction:
    return SourceExtraction(
        source="eu_startups",
        stable_id=stable_id,
        status="failed",
        reason=reason,
        source_url=source_url,
    )


def _website(container: Tag) -> tuple[str | None, str | None]:
    value = container.select_one(".wpbdp-field-website .value")
    if value is None:
        return None, None
    anchor = value.find("a", href=True)
    if anchor is None:
        return _text(value), None

    label = _text(anchor)
    href = anchor.get("href")
    if not isinstance(href, str):
        return None, label
    href = href.strip()
    if not href or re.search(r"[\x00-\x20\x7f]", href):
        return None, label
    try:
        parsed = urlsplit(href)
        # Accessing .port validates malformed port syntax and range.
        _ = parsed.port
    except ValueError:
        return None, label
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname.lower() == "eu-startups.com"
        or parsed.hostname.lower().endswith(".eu-startups.com")
    ):
        return None, label
    return href, label


def normalize_eu_startups(payload: dict[str, object]) -> SourceExtraction:
    """Extract listing evidence from a Bronze ``{url, html, lastmod}`` payload.

    The function is offline and side-effect free. It only trusts fields inside
    the source's ``.wpbdp-listing-single`` container; page chrome never enters
    the normalized output.
    """
    raw_url = payload.get("url")
    raw_html = payload.get("html")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return _failed(None, "missing or invalid listing URL")
    source_url = raw_url.strip()
    try:
        stable_id = _slug_from_url(source_url)
    except ValueError, TypeError:
        stable_id = None
    if stable_id is None:
        return _failed(None, "invalid EU-Startups listing URL", source_url)
    if not isinstance(raw_html, str) or not raw_html.strip():
        return _failed(stable_id, "missing or invalid HTML payload", source_url)

    source_times: dict[str, object] = {}
    if "lastmod" in payload:
        raw_lastmod = payload["lastmod"]
        if not isinstance(raw_lastmod, str) or not raw_lastmod.strip():
            return _failed(stable_id, "invalid listing lastmod", source_url)
        try:
            lastmod = datetime.fromisoformat(raw_lastmod.strip())
        except ValueError:
            return _failed(stable_id, "invalid listing lastmod", source_url)
        if lastmod.utcoffset() is None:
            return _failed(stable_id, "listing lastmod has no timezone", source_url)
        source_times["lastmod"] = lastmod

    soup = BeautifulSoup(raw_html, "html.parser")
    listing = soup.select_one(".wpbdp-listing-single")
    if listing is None:
        return _failed(stable_id, "listing container not found", source_url)

    source_fields: dict[str, object] = {}
    for output_name, slug in _FIELD_SELECTORS.items():
        value = _text(listing.select_one(f".wpbdp-field-{slug} .value"))
        source_fields[output_name] = value
    # Category text may contain a country label, but the source has no dedicated
    # country field, so it remains category evidence and is not copied to country.
    website, website_label = _website(listing)
    source_fields["website"] = website
    if website_label is not None:
        source_fields["website_label"] = website_label

    evidence = [value for value in source_fields.values() if isinstance(value, str)]
    if not evidence:
        return _failed(
            stable_id, "listing contains no supported source fields", source_url
        )

    title_element = listing.select_one(".listing-title")
    title = _text(title_element)
    if title is None and soup.title is not None:
        title = _text(soup.title)
        if title and title.endswith("| EU-Startups"):
            title = title[: -len("| EU-Startups")].strip() or None

    normalized_lines = [f"Listing: {title or stable_id}"]
    normalized_lines.extend(
        f"{name}: {value}"
        for name, value in source_fields.items()
        if isinstance(value, str)
    )
    normalized_text = "\n".join(normalized_lines)

    return SourceExtraction(
        source="eu_startups",
        stable_id=stable_id,
        status="captured",
        source_url=source_url,
        normalized_text=normalized_text,
        source_fields=source_fields,
        source_times=source_times,
    )
