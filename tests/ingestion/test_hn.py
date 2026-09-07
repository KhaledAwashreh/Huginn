from __future__ import annotations

import requests

from huginn.ingestion.adapters import hn


def test_get_json_returns_none_for_bare_null_body(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return None

    monkeypatch.setattr(hn.requests, "get", lambda url, timeout: FakeResponse())

    assert hn._get_json("https://example.invalid/item/1.json") is None


def test_get_json_returns_parsed_dict_body(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": 1, "type": "story"}

    monkeypatch.setattr(hn.requests, "get", lambda url, timeout: FakeResponse())

    assert hn._get_json("https://example.invalid/item/1.json") == {"id": 1, "type": "story"}


def test_get_json_raises_on_non_2xx_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error")

        def json(self):
            raise AssertionError("json() must not be called after raise_for_status raises")

    monkeypatch.setattr(hn.requests, "get", lambda url, timeout: FakeResponse())

    try:
        hn._get_json("https://example.invalid/item/1.json")
        raise AssertionError("expected requests.HTTPError")
    except requests.HTTPError:
        pass
