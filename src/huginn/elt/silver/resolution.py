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


class KeyDerivation:
    """The three entity-resolution bands from architecture document section
    6, naming how `resolved_company_key` was derived for a row, not
    whether it was compared against anything: this is a one-sided
    normalization/candidate-key step (Fellegi-Sunter "blocking", AWS
    Entity Resolution's "Normalization"), distinct from actual record
    matching, which is what FUZZY_MATCHED will be once KAN-4 builds it.
    """

    DOMAIN_NORMALIZED = "domain_normalized"
    FUZZY_MATCHED = "fuzzy_matched"
    UNRESOLVED = "unresolved"


def fuzzy_match(name: str, candidates: list[str]) -> tuple[str | None, float, str]:
    """Jaro-Winkler plus token-Jaccard fallback. Not implemented (Jira KAN-4):
    this is the researched-but-not-personally-verified recipe accepted as
    debt in architecture document section 6, to be properly learned once
    the manual-review queue accumulates a real backlog.
    """
    raise NotImplementedError("Entity resolution fuzzy fallback: see Jira KAN-4")
