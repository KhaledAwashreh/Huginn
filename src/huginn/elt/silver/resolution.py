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
import logging
import socket
from collections.abc import Callable
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

REACHABILITY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

# CGNAT shared address space (RFC 6598): not private/loopback/link-local/
# reserved by ipaddress's own properties, so it needs an explicit check.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _resolves_to_public_address(domain: str) -> bool:
    """Check if domain resolves to a public IP address.

    Returns False on DNS failure (including a malformed domain, e.g. an
    empty label or an overlong label, both of which surface as
    UnicodeError/ValueError from the idna codec rather than
    socket.gaierror) or if any resolved address is private, loopback,
    link-local, reserved, multicast, site-local (IPv6 only), or CGNAT
    shared address space (RFC 6598, 100.64.0.0/10). Returns True only if
    every resolved address is a normal public address.
    """
    try:
        results = socket.getaddrinfo(domain, 443)
    except socket.gaierror, UnicodeError, ValueError:
        return False

    for result in results:
        ip_str = result[4][0]
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip in _CGNAT_NETWORK
            or (ip.version == 6 and ip.is_site_local)
        ):
            logger.warning(
                "silver.resolution _resolves_to_public_address: rejecting "
                "%s, resolved address %s is not a routable public address",
                domain,
                ip_str,
            )
            return False

    return True


def _request_with_retry(
    method: Callable[..., requests.Response],
    url: str,
    timeout: float,
    headers: dict[str, str],
) -> requests.Response | None:
    """Issue one request, retrying once on Timeout/ConnectionError.

    Always passes allow_redirects=False. requests.get() defaults to
    allow_redirects=True, and a public domain redirecting to an internal
    address would otherwise bypass the SSRF DNS check entirely, since that
    check only validates the original hostname, not a redirect target
    (Jira KAN-62 Global Constraint 1).

    Returns None if the retry also raises Timeout/ConnectionError, or if
    any attempt raises another RequestException.
    """
    for attempt in range(2):
        try:
            return method(
                url,
                timeout=timeout,
                headers=headers,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout, requests.ConnectionError:
            if attempt == 0:
                continue
            return None
        except requests.RequestException:
            return None
    return None


def check_domain_reachable(domain: str, timeout: float = 5.0) -> bool:
    """Check if a domain is reachable via HTTP HEAD/GET.

    See Jira KAN-62 for overall design. Global Constraint 1 describes the
    SSRF-TOCTOU limitation (mitigated here by rejecting private/loopback/
    link-local/reserved/multicast/site-local/CGNAT addresses up front and
    disabling redirects on every request this module makes). Transient-retry
    mitigation: see Global Constraint 3. Parking-page exclusion: see
    Global Constraint 4.

    HEAD fallback to GET is triggered if HEAD fails (connection error,
    timeout, or any other exception that returns None from _request_with_retry)
    or returns a response outside the 200-399 range. This handles both WAF/CDN
    rejections of HEAD (which commonly return 400, 403, 501, etc., not just 405)
    and hosts that drop/refuse HEAD entirely but serve GET normally.
    """
    if not _resolves_to_public_address(domain):
        return False

    url = f"https://{domain}"
    headers = {"User-Agent": REACHABILITY_USER_AGENT}

    response = _request_with_retry(requests.head, url, timeout, headers)
    if response is None or not (200 <= response.status_code < 400):
        if response is not None:
            response.close()
        response = _request_with_retry(requests.get, url, timeout, headers)

    reachable = response is not None and 200 <= response.status_code < 400
    if response is not None:
        response.close()
    # DEBUG, not INFO: matching this codebase's existing precedent for
    # per-entity calls inside a batch loop (StatePort.last_hash) — logging
    # every one of ~6,000+ per-run domain checks at INFO would flood the log.
    logger.debug(
        "silver.resolution check_domain_reachable: %s %s",
        domain,
        "reachable" if reachable else "unreachable",
    )
    return reachable


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
