"""Entity resolution. See architecture document section 6.

Domain is the canonical key first. Where no domain match exists, the
fallback (normalize name, strip legal suffixes, Jaro-Winkler plus
token-Jaccard) is accepted technical debt adopted without the author's
own background in entity resolution (Jira KAN-4) and is not implemented
here yet. The domain-normalization step below is implemented since it is
simple and unambiguous; the fuzzy fallback is not, to avoid pretending a
researched-but-unverified recipe is production-ready.
"""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_domain(url_or_domain: str) -> str:
    """Registrable domain, normalized: lowercase, no `www.`, no protocol,
    no trailing slash or path. See architecture document section 6.
    """
    value = url_or_domain.strip().lower()
    if "//" not in value:
        value = f"//{value}"
    parsed = urlparse(value)
    host = parsed.hostname or parsed.path
    host = host.split("/")[0]
    if host.startswith("www."):
        host = host[len("www.") :]
    return host


class MatchConfidence:
    """The three entity-resolution bands from architecture document section 6."""

    AUTO_MATCHED = "auto_matched"
    MANUAL_REVIEW = "manual_review"
    NO_EXISTING_MATCH = "no_existing_match"


def fuzzy_match(name: str, candidates: list[str]) -> tuple[str | None, float, str]:
    """Jaro-Winkler plus token-Jaccard fallback. Not implemented (Jira KAN-4):
    this is the researched-but-not-personally-verified recipe accepted as
    debt in architecture document section 6, to be properly learned once
    the manual-review queue accumulates a real backlog.
    """
    raise NotImplementedError("Entity resolution fuzzy fallback: see Jira KAN-4")
