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

import ipaddress
import socket
from urllib.parse import urlparse

import requests

REACHABILITY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"


def _resolves_to_public_address(domain: str) -> bool:
    """Check if domain resolves to a public IP address.

    Returns False on DNS failure or if any resolved address is private,
    loopback, link-local, or reserved. Returns True only if at least one
    resolved address is a normal public address.
    """
    try:
        results = socket.getaddrinfo(domain, 443)
    except socket.gaierror:
        return False

    for result in results:
        ip_str = result[4][0]
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False

    return len(results) > 0


def check_domain_reachable(domain: str, timeout: float = 5.0) -> bool:
    """Check if a domain is reachable via HTTP HEAD/GET.

    SSRF-TOCTOU limitation: see KAN-62. Transient-retry mitigation: see
    Global Constraint 3. Parking-page exclusion: see Global Constraint 4.
    """
    if not _resolves_to_public_address(domain):
        return False

    url = f"https://{domain}"
    headers = {"User-Agent": REACHABILITY_USER_AGENT}

    try:
        response = requests.head(url, timeout=timeout, headers=headers)
    except requests.Timeout, requests.ConnectionError:
        try:
            response = requests.head(url, timeout=timeout, headers=headers)
        except requests.Timeout, requests.ConnectionError:
            return False
        except requests.RequestException:
            return False
    except requests.RequestException:
        return False

    if response.status_code == 405:
        try:
            response = requests.get(url, timeout=timeout, headers=headers)
        except requests.Timeout, requests.ConnectionError:
            try:
                response = requests.get(url, timeout=timeout, headers=headers)
            except requests.Timeout, requests.ConnectionError:
                return False
            except requests.RequestException:
                return False
        except requests.RequestException:
            return False

    return 200 <= response.status_code < 400


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
