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


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


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
        resolution.requests, "head", lambda url, timeout, headers: _FakeResponse(200)
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_true_on_head_3xx(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests, "head", lambda url, timeout, headers: _FakeResponse(301)
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_false_on_head_4xx(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests, "head", lambda url, timeout, headers: _FakeResponse(404)
    )

    assert check_domain_reachable("example.com") is False


def test_check_domain_reachable_falls_back_to_get_on_405(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(
        resolution.requests, "head", lambda url, timeout, headers: _FakeResponse(405)
    )
    monkeypatch.setattr(
        resolution.requests, "get", lambda url, timeout, headers: _FakeResponse(200)
    )

    assert check_domain_reachable("example.com") is True


def test_check_domain_reachable_false_on_dns_failure(monkeypatch):
    def _raise(host, port):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(resolution.socket, "getaddrinfo", _raise)

    assert check_domain_reachable("this-does-not-exist.invalid") is False


def test_check_domain_reachable_retries_once_on_timeout_then_succeeds(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    calls = {"n": 0}

    def flaky_head(url, timeout, headers):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.Timeout("slow")
        return _FakeResponse(200)

    monkeypatch.setattr(resolution.requests, "head", flaky_head)

    assert check_domain_reachable("example.com") is True
    assert calls["n"] == 2


def test_check_domain_reachable_false_after_two_consecutive_timeouts(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")

    def always_timeout(url, timeout, headers):
        raise requests.Timeout("slow")

    monkeypatch.setattr(resolution.requests, "head", always_timeout)

    assert check_domain_reachable("example.com") is False


def test_check_domain_reachable_sends_a_browser_user_agent(monkeypatch):
    _patch_dns(monkeypatch, "93.184.216.34")
    seen_headers = {}

    def fake_head(url, timeout, headers):
        seen_headers.update(headers)
        return _FakeResponse(200)

    monkeypatch.setattr(resolution.requests, "head", fake_head)

    check_domain_reachable("example.com")

    assert "Mozilla" in seen_headers.get("User-Agent", "")


def test_check_domain_reachable_false_for_loopback_address(monkeypatch):
    _patch_dns(monkeypatch, "127.0.0.1")

    assert check_domain_reachable("localhost") is False


def test_check_domain_reachable_false_for_link_local_metadata_address(monkeypatch):
    _patch_dns(monkeypatch, "169.254.169.254")

    assert check_domain_reachable("metadata.internal.invalid") is False


def test_check_domain_reachable_false_for_private_rfc1918_address(monkeypatch):
    _patch_dns(monkeypatch, "10.0.0.5")

    assert check_domain_reachable("internal.invalid") is False
