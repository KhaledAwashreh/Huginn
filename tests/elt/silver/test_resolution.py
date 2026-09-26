import socket

import requests

from huginn.elt.silver import resolution
from huginn.elt.silver.resolution import check_domain_reachable, normalize_domain


def test_normalize_domain_strips_protocol_and_www():
    assert normalize_domain("https://www.Acme.AI/careers") == "acme.ai"


def test_normalize_domain_handles_bare_domain():
    assert normalize_domain("acme.ai") == "acme.ai"


def test_normalize_domain_strips_trailing_path():
    assert normalize_domain("http://acme.ai/jobs/backend-engineer") == "acme.ai"


def test_normalize_domain_strips_port():
    assert normalize_domain("https://greenhouse.io:443/jobs") == "greenhouse.io"


def test_normalize_domain_strips_userinfo():
    assert normalize_domain("https://user@greenhouse.io/jobs") == "greenhouse.io"


def test_normalize_domain_strips_userinfo_and_port_together():
    assert (
        normalize_domain("https://user:pass@greenhouse.io:8080/jobs") == "greenhouse.io"
    )


def test_normalize_domain_strips_trailing_dot_from_fqdn():
    """DNS root label (trailing dot) in an absolute FQDN must be stripped.
    See Jira KAN-69."""
    assert normalize_domain("https://acme.bamboohr.com./jobs") == "acme.bamboohr.com"


def test_normalize_domain_strips_trailing_dot_from_bare_domain():
    """Bare domain with trailing dot must be normalized to remove it."""
    assert normalize_domain("acme.com.") == "acme.com"


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def close(self):
        """No-op close method for compatibility with stream=True."""
        pass


def _patch_dns(monkeypatch, ip: str):
    """Point getaddrinfo at a fixed IP so the SSRF pre-check and the
    reachability call see a deterministic address."""
    monkeypatch.setattr(
        resolution.socket,
        "getaddrinfo",
        lambda host, port: [(None, None, None, None, (ip, port))],
    )


def test_check_domain_reachable_true_on_head_2xx(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")  # public IP, example.com-range
    monkeypatch.setattr(
        resolution.requests,
        "head",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(200),
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_true_on_head_3xx(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests,
        "head",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(301),
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_false_on_head_4xx(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests,
        "head",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(404),
    )
    # HEAD 4xx now falls back to GET (see the 403 test below); mock GET too
    # so the fallback also fails and the overall result stays False.
    monkeypatch.setattr(
        resolution.requests,
        "get",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(404),
    )

    assert check_domain_reachable("example.com") is False


def test_check_domain_reachable_falls_back_to_get_on_405(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests,
        "head",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(405),
    )
    monkeypatch.setattr(
        resolution.requests,
        "get",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(200),
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_falls_back_to_get_on_403(monkeypatch):
    """WAFs/CDNs (e.g. Cloudflare bot-mitigation) commonly reject HEAD with
    403, not only 405. Any non-2xx/3xx HEAD response should trigger the GET
    fallback (Jira KAN-62)."""
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests,
        "head",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(403),
    )
    monkeypatch.setattr(
        resolution.requests,
        "get",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(200),
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_false_on_dns_failure(monkeypatch):
    def _raise(host, port):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(resolution.socket, "getaddrinfo", _raise)

    assert check_domain_reachable("this-does-not-exist.invalid") is False


def test_check_domain_reachable_false_for_malformed_domain_empty_label():
    """socket.getaddrinfo raises UnicodeEncodeError (a ValueError subclass)
    on malformed input such as an empty DNS label, not just
    socket.gaierror. A malformed domain must not crash the batch
    (Jira KAN-62)."""
    assert check_domain_reachable("acme..com") is False


def test_check_domain_reachable_false_for_malformed_domain_overlong_label():
    assert check_domain_reachable("a" * 300 + ".com") is False


def test_check_domain_reachable_retries_once_on_timeout_then_succeeds(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    calls = {"n": 0}

    def flaky_head(url, timeout, headers, allow_redirects, stream=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.Timeout("slow")
        return _FakeResponse(200)

    monkeypatch.setattr(resolution.requests, "head", flaky_head)

    assert check_domain_reachable("example.com") is True
    assert calls["n"] == 2


def test_check_domain_reachable_false_after_two_consecutive_timeouts(monkeypatch):
    """When HEAD times out twice, it returns None and GET is attempted. If
    GET also fails (whether by timeout or bad status), the overall result
    is False."""
    _patch_dns(monkeypatch, "93.184.216.34")

    def always_timeout(url, timeout, headers, allow_redirects, stream=None):
        raise requests.Timeout("slow")

    monkeypatch.setattr(resolution.requests, "head", always_timeout)
    monkeypatch.setattr(resolution.requests, "get", always_timeout)

    assert check_domain_reachable("example.com") is False


def test_check_domain_reachable_sends_a_browser_user_agent(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    seen_headers = {}

    def fake_head(url, timeout, headers, allow_redirects, stream=None):
        seen_headers.update(headers)
        return _FakeResponse(200)

    monkeypatch.setattr(resolution.requests, "head", fake_head)

    check_domain_reachable("example.com")

    assert "Mozilla" in seen_headers.get("User-Agent", "")


def test_check_domain_reachable_head_disables_redirects(monkeypatch):
    """requests.head() defaults allow_redirects=False and requests.get()
    defaults allow_redirects=True; a redirect to an internal address on
    either call would bypass the pre-connect SSRF DNS check entirely, so
    both calls must pass allow_redirects=False explicitly (Jira KAN-62
    Global Constraint 1)."""
    _patch_dns(monkeypatch, "93.184.216.34")
    seen = {}

    def fake_head(url, timeout, headers, **kwargs):
        seen["head"] = kwargs
        return _FakeResponse(200)

    monkeypatch.setattr(resolution.requests, "head", fake_head)

    check_domain_reachable("example.com")

    assert "allow_redirects" in seen["head"]
    assert seen["head"]["allow_redirects"] is False


def test_check_domain_reachable_get_fallback_disables_redirects(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    seen = {}

    monkeypatch.setattr(
        resolution.requests,
        "head",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(405),
    )

    def fake_get(url, timeout, headers, **kwargs):
        seen["get"] = kwargs
        return _FakeResponse(200)

    monkeypatch.setattr(resolution.requests, "get", fake_get)

    check_domain_reachable("example.com")

    assert "allow_redirects" in seen["get"]
    assert seen["get"]["allow_redirects"] is False


def test_check_domain_reachable_false_for_loopback_address(monkeypatch):
    _patch_dns(monkeypatch, "127.0.0.1")

    assert check_domain_reachable("localhost") is False


def test_check_domain_reachable_false_for_link_local_metadata_address(monkeypatch):
    _patch_dns(monkeypatch, "169.254.169.254")

    assert check_domain_reachable("metadata.internal.invalid") is False


def test_check_domain_reachable_false_for_private_rfc1918_address(monkeypatch):
    _patch_dns(monkeypatch, "10.0.0.5")

    assert check_domain_reachable("internal.invalid") is False


def test_check_domain_reachable_false_for_multicast_address(monkeypatch):
    _patch_dns(monkeypatch, "224.0.0.1")

    assert check_domain_reachable("multicast.internal.invalid") is False


def test_check_domain_reachable_false_for_cgnat_address(monkeypatch):
    _patch_dns(monkeypatch, "100.64.0.5")

    assert check_domain_reachable("cgnat.internal.invalid") is False


def test_check_domain_reachable_logs_warning_on_ssrf_rejection(monkeypatch, caplog):
    _patch_dns(monkeypatch, "127.0.0.1")

    with caplog.at_level("WARNING", logger=resolution.logger.name):
        check_domain_reachable("localhost")

    assert any(record.levelname == "WARNING" for record in caplog.records)


def test_check_domain_reachable_logs_debug_on_outcome(monkeypatch, caplog):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests,
        "head",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(200),
    )

    with caplog.at_level("DEBUG", logger=resolution.logger.name):
        check_domain_reachable("example.com")

    assert any(record.levelname == "DEBUG" for record in caplog.records)


def test_check_domain_reachable_false_for_ipv6_site_local_address(monkeypatch):
    """IPv6 site-local addresses (fec0::/10, deprecated by RFC 3879) must be
    rejected as part of the SSRF guard. ipaddress.IPv6Address has a dedicated
    .is_site_local property for this range (KAN-62)."""
    _patch_dns(monkeypatch, "fec0::1")

    assert check_domain_reachable("site-local.internal.invalid") is False


def test_check_domain_reachable_falls_back_to_get_on_head_connection_error(monkeypatch):
    """If HEAD fails with a connection error (not just a bad HTTP response),
    the function must still attempt GET. A host that drops HEAD outright but
    serves GET should not be wrongly marked unreachable (KAN-62)."""
    _patch_dns(monkeypatch, "93.184.216.34")

    def head_connection_error(url, timeout, headers, allow_redirects, stream=None):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(resolution.requests, "head", head_connection_error)
    monkeypatch.setattr(
        resolution.requests,
        "get",
        lambda url, timeout, headers, allow_redirects, stream=None: _FakeResponse(200),
    )

    assert check_domain_reachable("example.com") is True
