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


ROOT_ID = 49522897

WHOISHIRING_USER_JSON = {"submitted": [ROOT_ID, ROOT_ID - 1]}
ROOT_ITEM = {
    "id": ROOT_ID,
    "type": "story",
    "title": "Ask HN: Who is hiring? (September 2026)",
    "kids": [],
}


def test_discover_thread_item_returns_matching_submission(monkeypatch):
    fixtures = {
        f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
        f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM,
    }
    monkeypatch.setattr(hn, "_get_json", lambda url: fixtures[url])

    assert hn._discover_thread_item() == ROOT_ITEM


def test_discover_thread_item_raises_when_title_does_not_match(monkeypatch):
    mismatched_item = {"id": ROOT_ID, "title": "Ask HN: Something else", "kids": []}
    fixtures = {
        f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
        f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": mismatched_item,
    }
    monkeypatch.setattr(hn, "_get_json", lambda url: fixtures[url])

    try:
        hn._discover_thread_item()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "does not look like a Who's Hiring thread" in str(exc)


def test_discover_thread_item_raises_when_candidate_is_bare_null(monkeypatch):
    fixtures = {
        f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
        f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": None,
    }
    monkeypatch.setattr(hn, "_get_json", lambda url: fixtures[url])

    try:
        hn._discover_thread_item()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "does not look like a Who's Hiring thread" in str(exc)
