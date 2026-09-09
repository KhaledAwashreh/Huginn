from __future__ import annotations

import logging

import requests

from huginn.ingestion.adapters import yc
from huginn.ingestion.ports import ApiSourcePort, RawRecord


def test_yc_directory_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in yc.YcDirectoryAdapter.__mro__


def test_yc_directory_adapter_source_and_mechanism_unchanged():
    adapter = yc.YcDirectoryAdapter()
    assert adapter.source == "yc"
    assert adapter.mechanism == "api"


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


def test_discover_batches_requests_batch_facet_with_zero_hits(monkeypatch):
    captured = {}

    def fake_algolia_query(body):
        captured["body"] = body
        return {"facets": {"batch": {}}}

    monkeypatch.setattr(yc, "_algolia_query", fake_algolia_query)

    yc._discover_batches()

    assert captured["body"] == {
        "query": "",
        "facets": ["batch"],
        "hitsPerPage": 0,
        "maxValuesPerFacet": 1000,
    }


def test_discover_batches_returns_facet_keys(monkeypatch):
    facets_response = {"facets": {"batch": {"Summer 2026": 120, "Spring 2026": 95}}}
    monkeypatch.setattr(yc, "_algolia_query", lambda body: facets_response)

    batches = yc._discover_batches()

    assert set(batches) == {"Summer 2026", "Spring 2026"}


def test_discover_batches_returns_empty_list_when_no_facet_values(monkeypatch):
    monkeypatch.setattr(yc, "_algolia_query", lambda body: {"facets": {"batch": {}}})

    assert yc._discover_batches() == []


def test_fetch_batch_requests_filtered_query(monkeypatch):
    captured = {}

    def fake_algolia_query(body):
        captured["body"] = body
        return {"hits": [{"id": 531}], "nbHits": 1}

    monkeypatch.setattr(yc, "_algolia_query", fake_algolia_query)

    yc._fetch_batch("Summer 2026")

    assert captured["body"] == {
        "query": "",
        "filters": "batch:'Summer 2026'",
        "hitsPerPage": yc.ALGOLIA_MAX_HITS_PER_QUERY,
        "page": 0,
    }


def test_fetch_batch_returns_raw_hits_list(monkeypatch):
    hits = [{"id": 531, "name": "A"}, {"id": 8, "name": "PlanGrid"}]
    monkeypatch.setattr(yc, "_algolia_query", lambda body: {"hits": hits, "nbHits": 2})

    assert yc._fetch_batch("Summer 2026") == hits


def test_fetch_batch_returns_empty_list_when_no_hits(monkeypatch):
    monkeypatch.setattr(yc, "_algolia_query", lambda body: {"hits": [], "nbHits": 0})

    assert yc._fetch_batch("Winter 2005") == []


def test_fetch_returns_one_record_per_hit_across_batches(monkeypatch):
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Summer 2026", "Winter 2012"])

    def fake_fetch_batch(batch):
        if batch == "Summer 2026":
            return [{"id": 531, "name": "A", "batch": batch}]
        return [{"id": 8, "name": "PlanGrid", "batch": batch}]

    monkeypatch.setattr(yc, "_fetch_batch", fake_fetch_batch)
    monkeypatch.setattr(yc, "_total_hit_count", lambda: 2)

    records = yc.YcDirectoryAdapter().fetch()

    stable_ids = {record.stable_id for record in records}
    assert stable_ids == {"531", "8"}


def test_fetch_payload_is_exact_raw_hit(monkeypatch):
    hit = {"id": 8, "name": "PlanGrid", "objectID": "8", "batch": "Winter 2012"}
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Winter 2012"])
    monkeypatch.setattr(yc, "_fetch_batch", lambda batch: [hit])
    monkeypatch.setattr(yc, "_total_hit_count", lambda: 1)

    records = yc.YcDirectoryAdapter().fetch()

    assert records == [RawRecord(stable_id="8", payload=hit)]


def test_fetch_stable_id_uses_id_not_object_id(monkeypatch):
    hit = {"id": 531, "objectID": "different-value"}
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Summer 2026"])
    monkeypatch.setattr(yc, "_fetch_batch", lambda batch: [hit])
    monkeypatch.setattr(yc, "_total_hit_count", lambda: 1)

    records = yc.YcDirectoryAdapter().fetch()

    assert records[0].stable_id == "531"


def test_fetch_returns_empty_list_when_no_batches_discovered(monkeypatch):
    monkeypatch.setattr(yc, "_discover_batches", lambda: [])

    def _unexpected_fetch_batch(batch):
        raise AssertionError("_fetch_batch should not be called with no batches")

    monkeypatch.setattr(yc, "_fetch_batch", _unexpected_fetch_batch)
    monkeypatch.setattr(yc, "_total_hit_count", lambda: 0)

    assert yc.YcDirectoryAdapter().fetch() == []


def test_fetch_propagates_a_genuine_batch_fetch_failure(monkeypatch):
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Summer 2026", "Winter 2012"])

    def fake_fetch_batch(batch):
        if batch == "Winter 2012":
            raise RuntimeError("simulated timeout")
        return [{"id": 1}]

    monkeypatch.setattr(yc, "_fetch_batch", fake_fetch_batch)

    try:
        yc.YcDirectoryAdapter().fetch()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "simulated timeout" in str(exc)


def test_total_hit_count_requests_zero_hits_and_returns_nb_hits(monkeypatch):
    captured = {}

    def fake_algolia_query(body):
        captured["body"] = body
        return {"hits": [], "nbHits": 6204}

    monkeypatch.setattr(yc, "_algolia_query", fake_algolia_query)

    assert yc._total_hit_count() == 6204
    assert captured["body"] == {"query": "", "hitsPerPage": 0}


def test_fetch_logs_warning_when_total_hit_count_does_not_match_records(monkeypatch, caplog):
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Summer 2026"])
    monkeypatch.setattr(yc, "_fetch_batch", lambda batch: [{"id": 531}])
    monkeypatch.setattr(yc, "_total_hit_count", lambda: 6204)

    with caplog.at_level(logging.WARNING, logger=yc.logger.name):
        yc.YcDirectoryAdapter().fetch()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "1" in warnings[0].getMessage()
    assert "6204" in warnings[0].getMessage()


def test_fetch_does_not_log_warning_when_total_hit_count_matches_records(monkeypatch, caplog):
    monkeypatch.setattr(yc, "_discover_batches", lambda: ["Summer 2026"])
    monkeypatch.setattr(yc, "_fetch_batch", lambda batch: [{"id": 531}])
    monkeypatch.setattr(yc, "_total_hit_count", lambda: 1)

    with caplog.at_level(logging.WARNING, logger=yc.logger.name):
        yc.YcDirectoryAdapter().fetch()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == []
