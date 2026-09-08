from __future__ import annotations

import pytest

from huginn.ingestion.adapters import yc
from huginn.ingestion.ports import ApiSourcePort


def test_yc_directory_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in yc.YcDirectoryAdapter.__mro__


def test_yc_directory_adapter_source_and_mechanism_unchanged():
    adapter = yc.YcDirectoryAdapter()
    assert adapter.source == "yc"
    assert adapter.mechanism == "api"


def test_yc_directory_adapter_fetch_still_not_implemented():
    adapter = yc.YcDirectoryAdapter()
    with pytest.raises(NotImplementedError):
        adapter.fetch()


def test_algolia_api_key_reads_env_var(monkeypatch):
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "test-secured-key")

    assert yc._algolia_api_key() == "test-secured-key"


def test_algolia_api_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv(yc.ALGOLIA_API_KEY_ENV_VAR, raising=False)

    try:
        yc._algolia_api_key()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert yc.ALGOLIA_API_KEY_ENV_VAR in str(exc)


def test_algolia_api_key_raises_when_empty(monkeypatch):
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "")

    try:
        yc._algolia_api_key()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert yc.ALGOLIA_API_KEY_ENV_VAR in str(exc)


import requests


def test_algolia_query_posts_expected_url_headers_and_body(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"hits": [], "nbHits": 0}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(yc.requests, "post", fake_post)
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "test-secured-key")

    result = yc._algolia_query({"query": ""})

    assert captured["url"] == yc.ALGOLIA_QUERY_URL
    assert captured["json"] == {"query": ""}
    assert captured["headers"] == {
        "X-Algolia-Application-Id": yc.ALGOLIA_APP_ID,
        "X-Algolia-API-Key": "test-secured-key",
    }
    assert captured["timeout"] == yc.REQUEST_TIMEOUT_SECONDS
    assert result == {"hits": [], "nbHits": 0}


def test_algolia_query_raises_on_non_2xx_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise requests.HTTPError("403 Forbidden")

        def json(self):
            raise AssertionError("json() must not be called after raise_for_status raises")

    monkeypatch.setattr(yc.requests, "post", lambda url, json, headers, timeout: FakeResponse())
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "test-secured-key")

    try:
        yc._algolia_query({"query": ""})
        raise AssertionError("expected requests.HTTPError")
    except requests.HTTPError:
        pass


def test_algolia_query_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv(yc.ALGOLIA_API_KEY_ENV_VAR, raising=False)

    try:
        yc._algolia_query({"query": ""})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert yc.ALGOLIA_API_KEY_ENV_VAR in str(exc)
