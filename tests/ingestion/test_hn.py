from __future__ import annotations

import requests

from huginn.ingestion.adapters import hn
from huginn.ingestion.ports import ApiSourcePort


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


KID_A_ID = 49573833
KID_B_ID = 49524098  # deleted stub
KID_C_ID = 49999999  # bare null, never existed

ROOT_ITEM_WITH_KIDS = {
    "id": ROOT_ID,
    "type": "story",
    "title": "Ask HN: Who is hiring? (September 2026)",
    "kids": [KID_A_ID, KID_B_ID, KID_C_ID],
}
KID_A_ITEM = {
    "id": KID_A_ID,
    "type": "comment",
    "parent": ROOT_ID,
    "by": "srikanthkasa",
    "text": "Supero | Cloud / Platform Engineer | REMOTE",
}
KID_B_DELETED_ITEM = {
    "id": KID_B_ID,
    "deleted": True,
    "parent": ROOT_ID,
    "time": 1788279499,
    "type": "comment",
}

FIREBASE_FIXTURES = {
    f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
    f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM_WITH_KIDS,
    f"{hn.FIREBASE_BASE_URL}/item/{KID_A_ID}.json": KID_A_ITEM,
    f"{hn.FIREBASE_BASE_URL}/item/{KID_B_ID}.json": KID_B_DELETED_ITEM,
    f"{hn.FIREBASE_BASE_URL}/item/{KID_C_ID}.json": None,
}


def _fake_get_json(url):
    return FIREBASE_FIXTURES[url]


def test_fetch_item_returns_none_for_bare_null(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    assert hn._fetch_item(KID_C_ID) is None


def test_fetch_item_returns_deleted_stub_as_is(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    assert hn._fetch_item(KID_B_ID) == KID_B_DELETED_ITEM


def test_fetch_returns_root_and_top_level_kids(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    records = hn.HackerNewsAdapter().fetch()

    stable_ids = {record.stable_id for record in records}
    assert stable_ids == {str(ROOT_ID), str(KID_A_ID), str(KID_B_ID)}


def test_fetch_skips_bare_null_kids(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    records = hn.HackerNewsAdapter().fetch()

    assert str(KID_C_ID) not in {record.stable_id for record in records}


def test_fetch_stores_deleted_stub_verbatim(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    records = hn.HackerNewsAdapter().fetch()

    deleted_record = next(r for r in records if r.stable_id == str(KID_B_ID))
    assert deleted_record.payload == KID_B_DELETED_ITEM


def test_fetch_payload_is_exact_root_item(monkeypatch):
    monkeypatch.setattr(hn, "_get_json", _fake_get_json)

    records = hn.HackerNewsAdapter().fetch()

    root_record = next(r for r in records if r.stable_id == str(ROOT_ID))
    assert root_record.payload == ROOT_ITEM_WITH_KIDS


def test_fetch_root_with_no_kids_returns_single_record(monkeypatch):
    fixtures = {
        f"{hn.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
        f"{hn.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM,
    }
    monkeypatch.setattr(hn, "_get_json", lambda url: fixtures[url])

    records = hn.HackerNewsAdapter().fetch()

    assert [r.stable_id for r in records] == [str(ROOT_ID)]


def test_fetch_propagates_a_genuine_kid_fetch_failure(monkeypatch):
    def _raising_get_json(url):
        if url == f"{hn.FIREBASE_BASE_URL}/item/{KID_A_ID}.json":
            raise RuntimeError("simulated timeout")
        return _fake_get_json(url)

    monkeypatch.setattr(hn, "_get_json", _raising_get_json)

    try:
        hn.HackerNewsAdapter().fetch()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "simulated timeout" in str(exc)


def test_hacker_news_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in hn.HackerNewsAdapter.__mro__
