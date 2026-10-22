"""Pure source lifecycle and identity policy; see architecture sections 4.2/6."""

from __future__ import annotations

import html
import ipaddress
import math
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from huginn.elt.silver.context.eu_startups import normalize_eu_startups
from huginn.elt.silver.context.hn import normalize_hn
from huginn.elt.silver.context.models import SourceExtraction
from huginn.elt.silver.context.yc import normalize_yc
from huginn.elt.silver.currentness.models import LifecycleFacts, LifecycleInput
from huginn.elt.silver.resolution import normalize_domain

_HN_HEADER_LINK = re.compile(r'<a\s+href="([^"]+)"', re.IGNORECASE)
_HN_PARAGRAPH_START = re.compile(r"<p(?:\s[^>]*)?>", re.IGNORECASE)
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def _matches_id(item: LifecycleInput, context: SourceExtraction) -> bool:
    return context.stable_id == item.stable_id


def _source_time(item: LifecycleInput) -> datetime | None:
    """Parse the source event time independently of other context fields."""
    if item.source == "hn":
        value = item.payload.get("time")
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except OverflowError, OSError, ValueError:
            return None
    if item.source == "yc":
        value = item.payload.get("launched_at")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            if not math.isfinite(value):
                return None
            return datetime.fromtimestamp(value, tz=UTC)
        except OverflowError, OSError, ValueError:
            return None
    value = item.payload.get("lastmod")
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
        return parsed if parsed.utcoffset() is not None else None
    return None


def _normalize_explicit_domain(value: object) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if any(ord(char) <= 0x20 or ord(char) == 0x7F for char in value):
        return None
    try:
        parsed = urlsplit(value if "://" in value else f"//{value}")
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        host = parsed.hostname
        if not host:
            return None
        # Touching .port validates malformed and out-of-range ports.
        _ = parsed.port
        ascii_host = host.encode("idna").decode("ascii").lower().rstrip(".")
    except ValueError:
        return None
    except UnicodeError, AttributeError:
        return None
    try:
        ipaddress.ip_address(ascii_host)
    except ValueError:
        pass
    else:
        return None

    if ascii_host.startswith("www."):
        ascii_host = ascii_host[4:]
    labels = ascii_host.split(".")
    if len(labels) < 2 or len(ascii_host) > 253:
        return None
    if any(not _DNS_LABEL.fullmatch(label) for label in labels):
        return None
    return normalize_domain(value)


def _identity(item: LifecycleInput, context: SourceExtraction) -> tuple[str, str]:
    domain = _normalize_explicit_domain(_explicit_website(item, context))
    if domain is None:
        return "missing", "no_explicit_domain"
    if (
        item.key_derivation is None
        or item.key_derivation != "domain_normalized"
        or item.resolved_company_key is None
    ):
        return "unresolved", "identity_resolution_not_domain_normalized"
    if domain == item.resolved_company_key:
        return "consistent", "explicit_domain_matches_resolved_key"
    return "mismatch", "explicit_domain_differs_from_resolved_key"


def _explicit_website(item: LifecycleInput, context: SourceExtraction) -> object:
    if item.source == "yc":
        return item.payload.get("website")
    if item.source == "eu_startups":
        return context.source_fields.get("website")
    raw_text = item.payload.get("text")
    if not isinstance(raw_text, str):
        return None
    paragraph = _HN_PARAGRAPH_START.search(raw_text)
    header = raw_text[: paragraph.start()] if paragraph else raw_text
    match = _HN_HEADER_LINK.search(header)
    return html.unescape(match.group(1)) if match else None


def _context(item: LifecycleInput) -> SourceExtraction:
    if item.source == "hn":
        return normalize_hn(item.payload)
    if item.source == "yc":
        return normalize_yc(item.payload)
    return normalize_eu_startups(item.payload)


def classify(item: LifecycleInput) -> LifecycleFacts:
    """Classify one current source observation without I/O or inferred demand."""
    if not isinstance(item.payload, dict):
        return LifecycleFacts(
            listing_state="invalid",
            hiring_state="unknown" if item.source in {"hn", "yc"} else "not_applicable",
            identity_state="missing",
            reason="malformed_payload",
            explicit_domain=None,
            occurred_at=None,
            context=SourceExtraction(
                source=item.source,
                stable_id=None,
                status="failed",
                reason="malformed_payload",
            ),
        )

    context = _context(item)
    listing_state = "invalid"
    hiring_state = "not_applicable"
    reason = "source_context_invalid"
    if item.source == "yc":
        hiring = item.payload.get("isHiring")
        if isinstance(hiring, bool):
            hiring_state = "true" if hiring else "false"
        else:
            hiring_state = "unknown"

    # A Bronze stable key is the boundary for every source-specific rule.
    if not _matches_id(item, context):
        reason = "stable_id_mismatch"
    elif item.source == "yc":
        status = item.payload.get("status")
        if isinstance(status, str) and status in {"Inactive", "Acquired"}:
            listing_state = "withdrawn"
            reason = "yc_status_withdrawn"
        elif isinstance(status, str) and status in {"Active", "Public"}:
            if context.status == "captured":
                listing_state = "available"
                reason = "yc_status_available"
            else:
                reason = "source_context_invalid"
        elif status is None or isinstance(status, str):
            if context.status == "captured":
                listing_state = "unknown"
                reason = "yc_status_unknown"
        else:
            reason = "malformed_yc_status"

    elif item.source == "hn":
        payload = item.payload
        item_type = payload.get("type")
        if (
            item_type == "story"
            or payload.get("deleted") is True
            or payload.get("dead") is True
        ):
            listing_state = "withdrawn"
            reason = "hn_non_comment_or_tombstone"
            hiring_state = "true"
        elif item_type == "comment" and (
            payload.get("text") is None
            or payload.get("text") == ""
            or (context.status == "excluded" and context.reason == "empty_text")
        ):
            listing_state = "withdrawn"
            reason = "hn_empty_comment"
            hiring_state = "true"
        elif item_type == "comment" and context.status == "captured":
            listing_state = "available"
            reason = "hn_valid_comment"
            hiring_state = "true"
        elif item_type == "comment":
            reason = "source_context_invalid"
            hiring_state = "true"
        elif isinstance(item_type, str):
            listing_state = "withdrawn"
            reason = "hn_non_comment"
            hiring_state = "true"
        else:
            reason = "malformed_hn_type"
    elif item.source == "eu_startups":
        if context.status == "captured":
            listing_state = "available"
            reason = "eu_listing_captured"
        else:
            reason = "source_context_invalid"

    identity_state, _ = _identity(item, context)
    occurred_at = _source_time(item)
    explicit_domain = _normalize_explicit_domain(_explicit_website(item, context))
    return LifecycleFacts(
        listing_state=listing_state,  # type: ignore[arg-type]
        hiring_state=hiring_state,  # type: ignore[arg-type]
        identity_state=identity_state,  # type: ignore[arg-type]
        reason=reason,
        explicit_domain=explicit_domain,
        occurred_at=occurred_at,
        context=context,
    )
