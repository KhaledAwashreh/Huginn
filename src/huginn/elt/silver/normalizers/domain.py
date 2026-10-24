"""Pure domain normalization; see architecture section 6 and Jira KAN-69."""

from urllib.parse import urlparse


def normalize_domain(url_or_domain: str) -> str:
    """Normalize a hostname without network access or reachability checks."""
    value = url_or_domain.strip().lower()
    if "//" not in value:
        value = f"//{value}"
    parsed = urlparse(value)
    host = parsed.hostname or parsed.path
    host = host.split("/")[0]
    if host.startswith("www."):
        host = host[len("www.") :]
    if host.endswith("."):
        host = host[:-1]
    return host
