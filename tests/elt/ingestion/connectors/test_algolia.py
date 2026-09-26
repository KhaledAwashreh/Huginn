from __future__ import annotations

import requests

from huginn.elt.ingestion.connectors import algolia
from huginn.elt.ingestion.connectors.algolia import AlgoliaConnector

APP_ID = "45BWZJ1SGC"
INDEX = "YCCompany_production"


def _connector() -> AlgoliaConnector:
    return AlgoliaConnector(app_id=APP_ID, index=INDEX, api_key="test-secured-key")


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

    monkeypatch.setattr(algolia.requests, "post", fake_post)

    result = _connector().query({"query": ""})

    assert captured["url"] == (
        f"https://{APP_ID}-dsn.algolia.net/1/indexes/{INDEX}/query"
    )
    assert captured["json"] == {"query": ""}
    assert captured["headers"] == {
        "X-Algolia-Application-Id": APP_ID,
        "X-Algolia-API-Key": "test-secured-key",
    }
    # Pinned as a literal, not as `algolia.DEFAULT_TIMEOUT_SECONDS`: asserting
    # against the constant would pass unchanged if the constant changed, which
    # is the one thing this test exists to catch.
    assert captured["timeout"] == 10.0
    assert result == {"hits": [], "nbHits": 0}


def test_algolia_query_raises_on_non_2xx_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise requests.HTTPError("403 Forbidden")

        def json(self):
            raise AssertionError(
                "json() must not be called after raise_for_status raises"
            )

    monkeypatch.setattr(
        algolia.requests, "post", lambda url, json, headers, timeout: FakeResponse()
    )

    try:
        _connector().query({"query": ""})
        raise AssertionError("expected requests.HTTPError")
    except requests.HTTPError:
        pass


def test_discover_batches_requests_batch_facet_with_zero_hits(monkeypatch):
    captured = {}

    def fake_query(self, body):
        captured["body"] = body
        return {"facets": {"batch": {}}}

    monkeypatch.setattr(AlgoliaConnector, "query", fake_query)

    _connector().discover_batches()

    assert captured["body"] == {
        "query": "",
        "facets": ["batch"],
        "hitsPerPage": 0,
        "maxValuesPerFacet": 1000,
    }


def test_discover_batches_returns_facet_keys(monkeypatch):
    facets_response = {"facets": {"batch": {"Summer 2026": 120, "Spring 2026": 95}}}
    monkeypatch.setattr(AlgoliaConnector, "query", lambda self, body: facets_response)

    batches = _connector().discover_batches()

    assert set(batches) == {"Summer 2026", "Spring 2026"}


def test_discover_batches_returns_empty_list_when_no_facet_values(monkeypatch):
    monkeypatch.setattr(
        AlgoliaConnector, "query", lambda self, body: {"facets": {"batch": {}}}
    )

    assert _connector().discover_batches() == []


def test_fetch_batch_requests_filtered_query(monkeypatch):
    captured = {}

    def fake_query(self, body):
        captured["body"] = body
        return {"hits": [{"id": 531}], "nbHits": 1}

    monkeypatch.setattr(AlgoliaConnector, "query", fake_query)

    _connector().fetch_batch("Summer 2026")

    assert captured["body"] == {
        "query": "",
        "facetFilters": [["batch:Summer 2026"]],
        "hitsPerPage": algolia.ALGOLIA_MAX_HITS_PER_QUERY,
        "page": 0,
    }


def test_fetch_batch_handles_a_batch_value_containing_an_apostrophe(monkeypatch):
    """facetFilters needs no quoting, unlike the old `filters: "batch:'{batch}'"`
    string, which would have produced a malformed expression for a batch
    value containing an apostrophe."""
    captured = {}

    def fake_query(self, body):
        captured["body"] = body
        return {"hits": [], "nbHits": 0}

    monkeypatch.setattr(AlgoliaConnector, "query", fake_query)

    _connector().fetch_batch("Founder's Batch")

    assert captured["body"]["facetFilters"] == [["batch:Founder's Batch"]]


def test_fetch_batch_returns_raw_hits_list(monkeypatch):
    hits = [{"id": 531, "name": "A"}, {"id": 8, "name": "PlanGrid"}]
    monkeypatch.setattr(
        AlgoliaConnector, "query", lambda self, body: {"hits": hits, "nbHits": 2}
    )

    assert _connector().fetch_batch("Summer 2026") == hits


def test_fetch_batch_returns_empty_list_when_no_hits(monkeypatch):
    monkeypatch.setattr(
        AlgoliaConnector, "query", lambda self, body: {"hits": [], "nbHits": 0}
    )

    assert _connector().fetch_batch("Winter 2005") == []


def test_total_hit_count_requests_zero_hits_and_returns_nb_hits(monkeypatch):
    captured = {}

    def fake_query(self, body):
        captured["body"] = body
        return {"hits": [], "nbHits": 6204}

    monkeypatch.setattr(AlgoliaConnector, "query", fake_query)

    assert _connector().total_hit_count() == 6204
    assert captured["body"] == {"query": "", "hitsPerPage": 0}
