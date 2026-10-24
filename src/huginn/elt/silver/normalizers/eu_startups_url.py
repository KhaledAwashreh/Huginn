"""Pure URL helpers for EU-Startups listing normalization."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse


def _slug_from_url(url: str) -> str | None:
    """The listing's directory slug from its detail-page URL, mirroring
    huginn.elt.ingestion.adapters.eu_startups's `_listing_slug` (used
    there as `RawRecord.stable_id`). Reused here as this staging row's
    `stable_id` since the Bronze payload itself carries only
    `{"url", "html", "lastmod"}`, no separately-captured id. Returns None
    unless the URL is a valid HTTPS EU-Startups listing URL.
    """
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.eu-startups.com"
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    match = re.fullmatch(r"/directory/([^/]+)/?", parsed.path)
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
