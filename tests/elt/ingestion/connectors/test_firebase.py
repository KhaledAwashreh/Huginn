from __future__ import annotations

import requests

from huginn.elt.ingestion.connectors import firebase
from huginn.elt.ingestion.connectors.firebase import FirebaseConnector

ITEM_ID = 49573833


class _FakeResponse:
    """Minimal stand-in for a `requests.Response`."""

    def __init__(self, body, error=None) -> None:
        """Capture the body `json()` should return, or the error
        `raise_for_status()` should raise.
        """
        self._body = body
        self._error = error

    def raise_for_status(self):
        """Raise the configured error, or do nothing when there is none."""
        if self._error is not None:
            raise self._error

    def json(self):
        """Return the configured body."""
        return self._body


def test_get_item_requests_the_expected_url_and_timeout(monkeypatch):
    """The connector owns the URL shape, so it is asserted here rather than
    left implicit as it was when the adapter built the URL inline."""
    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse({"id": ITEM_ID})

    monkeypatch.setattr(firebase.requests, "get", fake_get)

    FirebaseConnector().get_item(ITEM_ID)

    assert captured["url"] == f"{firebase.FIREBASE_BASE_URL}/item/{ITEM_ID}.json"
    # Pinned as a literal, not as `firebase.DEFAULT_TIMEOUT_SECONDS`: asserting
    # against the constant would pass unchanged if the constant changed, which
    # is the one thing this test exists to catch.
    assert captured["timeout"] == 10.0


def test_get_user_requests_the_expected_url(monkeypatch):
    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        return _FakeResponse({"id": "whoishiring"})

    monkeypatch.setattr(firebase.requests, "get", fake_get)

    FirebaseConnector().get_user("whoishiring")

    assert captured["url"] == f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json"


def test_get_json_returns_none_for_bare_null_body(monkeypatch):
    """A body of the JSON literal `null` means the id never existed."""
    monkeypatch.setattr(
        firebase.requests, "get", lambda url, timeout: _FakeResponse(None)
    )

    assert FirebaseConnector().get_item(ITEM_ID) is None


def test_get_json_returns_parsed_dict_body(monkeypatch):
    monkeypatch.setattr(
        firebase.requests,
        "get",
        lambda url, timeout: _FakeResponse({"id": ITEM_ID, "type": "story"}),
    )

    assert FirebaseConnector().get_item(ITEM_ID) == {"id": ITEM_ID, "type": "story"}


def test_get_json_raises_on_non_2xx_response(monkeypatch):
    monkeypatch.setattr(
        firebase.requests,
        "get",
        lambda url, timeout: _FakeResponse(
            None, error=requests.HTTPError("500 Server Error")
        ),
    )

    try:
        FirebaseConnector().get_item(ITEM_ID)
        raise AssertionError("expected requests.HTTPError")
    except requests.HTTPError:
        pass


def test_get_item_returns_a_deleted_stub_as_is(monkeypatch):
    """A `deleted: true` stub is a real record, not a missing one, so it is
    returned verbatim rather than collapsed to None."""
    stub = {"id": ITEM_ID, "deleted": True, "type": "comment"}
    monkeypatch.setattr(
        firebase.requests, "get", lambda url, timeout: _FakeResponse(stub)
    )

    assert FirebaseConnector().get_item(ITEM_ID) == stub


def test_get_user_returns_none_for_bare_null_body(monkeypatch):
    monkeypatch.setattr(
        firebase.requests, "get", lambda url, timeout: _FakeResponse(None)
    )

    assert FirebaseConnector().get_user("whoishiring") is None
