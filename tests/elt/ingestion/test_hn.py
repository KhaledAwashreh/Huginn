from __future__ import annotations

from huginn.elt.ingestion.adapters import hn
from huginn.elt.ingestion.connectors import firebase
from huginn.elt.ingestion.ports import ApiSourcePort

ROOT_ID = 49522897

WHOISHIRING_USER_JSON = {"submitted": [ROOT_ID, ROOT_ID - 1]}
ROOT_ITEM = {
    "id": ROOT_ID,
    "type": "story",
    "title": "Ask HN: Who is hiring? (September 2026)",
    "kids": [],
}

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
    f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json": WHOISHIRING_USER_JSON,
    f"{firebase.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM_WITH_KIDS,
    f"{firebase.FIREBASE_BASE_URL}/item/{KID_A_ID}.json": KID_A_ITEM,
    f"{firebase.FIREBASE_BASE_URL}/item/{KID_B_ID}.json": KID_B_DELETED_ITEM,
    f"{firebase.FIREBASE_BASE_URL}/item/{KID_C_ID}.json": None,
}


class _FakeFirebaseConnector:
    """Stands in for `FirebaseConnector` so the adapter's policy is testable
    without a network call (CLAUDE.md code standard 4). Keys its fixtures by
    full URL, the shape the real connector builds, so `FIREBASE_FIXTURES` above
    is unchanged from before the extraction.
    """

    def __init__(self, fixtures=None, errors=None) -> None:
        """Default to the full fixture map; `errors` maps a URL to the
        exception it should raise.
        """
        self._fixtures = FIREBASE_FIXTURES if fixtures is None else fixtures
        self._errors = errors or {}
        self.requested: list[str] = []

    def get_user(self, user_id: str) -> dict | None:
        """Return the canned user profile."""
        return self._get(f"user/{user_id}.json")

    def get_item(self, item_id: int) -> dict | None:
        """Return the canned item, raising if this id is configured to fail."""
        return self._get(f"item/{item_id}.json")

    def _get(self, path: str) -> dict | None:
        url = f"{firebase.FIREBASE_BASE_URL}/{path}"
        self.requested.append(url)
        if url in self._errors:
            raise self._errors[url]
        return self._fixtures[url]


def test_hacker_news_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in hn.HackerNewsAdapter.__mro__


def test_hacker_news_adapter_source_and_mechanism_unchanged():
    adapter = hn.HackerNewsAdapter(firebase=_FakeFirebaseConnector())
    assert adapter.source == "hn"
    assert adapter.mechanism == "api"


def test_discover_thread_item_returns_matching_submission():
    connector = _FakeFirebaseConnector(
        fixtures={
            f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json": (
                WHOISHIRING_USER_JSON
            ),
            f"{firebase.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM,
        }
    )

    adapter = hn.HackerNewsAdapter(firebase=connector)

    assert adapter._discover_thread_item() == ROOT_ITEM
    assert connector.requested == [
        f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json",
        f"{firebase.FIREBASE_BASE_URL}/item/{ROOT_ID}.json",
    ]


def test_discover_thread_item_raises_when_title_does_not_match():
    mismatched_item = {"id": ROOT_ID, "title": "Ask HN: Something else", "kids": []}
    connector = _FakeFirebaseConnector(
        fixtures={
            f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json": (
                WHOISHIRING_USER_JSON
            ),
            f"{firebase.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": mismatched_item,
        }
    )

    try:
        hn.HackerNewsAdapter(firebase=connector)._discover_thread_item()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "does not look like a Who's Hiring thread" in str(exc)


def test_discover_thread_item_raises_when_candidate_is_bare_null():
    connector = _FakeFirebaseConnector(
        fixtures={
            f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json": (
                WHOISHIRING_USER_JSON
            ),
            f"{firebase.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": None,
        }
    )

    try:
        hn.HackerNewsAdapter(firebase=connector)._discover_thread_item()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "does not look like a Who's Hiring thread" in str(exc)


def test_discover_thread_item_raises_a_clear_error_when_the_user_response_is_null():
    connector = _FakeFirebaseConnector(
        fixtures={
            f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json": None,
            f"{firebase.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM,
        }
    )

    try:
        hn.HackerNewsAdapter(firebase=connector)._discover_thread_item()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "whoishiring" in str(exc)
        assert "user profile" in str(exc)


def test_discover_thread_item_raises_a_clear_error_when_submitted_is_empty():
    connector = _FakeFirebaseConnector(
        fixtures={
            f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json": {"submitted": []},
            f"{firebase.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM,
        }
    )

    try:
        hn.HackerNewsAdapter(firebase=connector)._discover_thread_item()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "whoishiring" in str(exc)
        assert "user profile" in str(exc)


def test_fetch_returns_root_and_top_level_kids():
    records = hn.HackerNewsAdapter(firebase=_FakeFirebaseConnector()).fetch()

    stable_ids = {record.stable_id for record in records}
    assert stable_ids == {str(ROOT_ID), str(KID_A_ID), str(KID_B_ID)}


def test_fetch_skips_bare_null_kids():
    records = hn.HackerNewsAdapter(firebase=_FakeFirebaseConnector()).fetch()

    assert str(KID_C_ID) not in {record.stable_id for record in records}


def test_fetch_stores_deleted_stub_verbatim():
    records = hn.HackerNewsAdapter(firebase=_FakeFirebaseConnector()).fetch()

    deleted_record = next(r for r in records if r.stable_id == str(KID_B_ID))
    assert deleted_record.payload == KID_B_DELETED_ITEM


def test_fetch_payload_is_exact_root_item():
    records = hn.HackerNewsAdapter(firebase=_FakeFirebaseConnector()).fetch()

    root_record = next(r for r in records if r.stable_id == str(ROOT_ID))
    assert root_record.payload == ROOT_ITEM_WITH_KIDS


def test_fetch_root_with_no_kids_returns_single_record():
    connector = _FakeFirebaseConnector(
        fixtures={
            f"{firebase.FIREBASE_BASE_URL}/user/whoishiring.json": (
                WHOISHIRING_USER_JSON
            ),
            f"{firebase.FIREBASE_BASE_URL}/item/{ROOT_ID}.json": ROOT_ITEM,
        }
    )

    records = hn.HackerNewsAdapter(firebase=connector).fetch()

    assert [r.stable_id for r in records] == [str(ROOT_ID)]


def test_fetch_propagates_a_genuine_kid_fetch_failure():
    connector = _FakeFirebaseConnector(
        errors={
            f"{firebase.FIREBASE_BASE_URL}/item/{KID_A_ID}.json": RuntimeError(
                "simulated timeout"
            )
        }
    )

    try:
        hn.HackerNewsAdapter(firebase=connector).fetch()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "simulated timeout" in str(exc)
