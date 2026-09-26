from __future__ import annotations

import logging

from huginn.elt.ingestion.adapters import yc
from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import ApiSourcePort


class _FakeAlgoliaConnector:
    """Stands in for `AlgoliaConnector` so the adapter's orchestration is
    testable without a network call (CLAUDE.md code standard 4). Records
    which batches it was asked for, so a test can assert the connector is
    untouched when the policy is not exercised.
    """

    def __init__(self, batches, hits_by_batch=None, total=0, errors=None) -> None:
        """Capture the canned responses for each of the connector's methods."""
        self._batches = list(batches)
        self._hits_by_batch = hits_by_batch or {}
        self._total = total
        self._errors = errors or {}
        self.fetch_batch_calls: list[str] = []

    def discover_batches(self) -> list[str]:
        """Return the canned batch facet values."""
        return list(self._batches)

    def fetch_batch(self, batch: str) -> list[dict]:
        """Return or raise the canned response for one batch."""
        self.fetch_batch_calls.append(batch)
        if batch in self._errors:
            raise self._errors[batch]
        return self._hits_by_batch.get(batch, [])

    def total_hit_count(self) -> int:
        """Return the canned directory total."""
        return self._total


def test_yc_directory_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in yc.YcDirectoryAdapter.__mro__


def test_yc_directory_adapter_source_and_mechanism_unchanged():
    adapter = yc.YcDirectoryAdapter(algolia=_FakeAlgoliaConnector(batches=[]))
    assert adapter.source == "yc"
    assert adapter.mechanism == "api"


def test_fetch_returns_one_record_per_hit_across_batches():
    connector = _FakeAlgoliaConnector(
        batches=["Summer 2026", "Winter 2012"],
        hits_by_batch={
            "Summer 2026": [{"id": 531, "name": "A", "batch": "Summer 2026"}],
            "Winter 2012": [{"id": 8, "name": "PlanGrid", "batch": "Winter 2012"}],
        },
        total=2,
    )

    records = yc.YcDirectoryAdapter(algolia=connector).fetch()

    stable_ids = {record.stable_id for record in records}
    assert stable_ids == {"531", "8"}


def test_fetch_payload_is_exact_raw_hit():
    hit = {"id": 8, "name": "PlanGrid", "objectID": "8", "batch": "Winter 2012"}
    connector = _FakeAlgoliaConnector(
        batches=["Winter 2012"], hits_by_batch={"Winter 2012": [hit]}, total=1
    )

    records = yc.YcDirectoryAdapter(algolia=connector).fetch()

    assert records == [RawRecord(stable_id="8", payload=hit)]


def test_fetch_stable_id_uses_id_not_object_id():
    hit = {"id": 531, "objectID": "different-value"}
    connector = _FakeAlgoliaConnector(
        batches=["Summer 2026"], hits_by_batch={"Summer 2026": [hit]}, total=1
    )

    records = yc.YcDirectoryAdapter(algolia=connector).fetch()

    assert records[0].stable_id == "531"


def test_fetch_returns_empty_list_when_no_batches_discovered():
    connector = _FakeAlgoliaConnector(batches=[], total=0)

    assert yc.YcDirectoryAdapter(algolia=connector).fetch() == []
    assert connector.fetch_batch_calls == []


def test_fetch_propagates_a_genuine_batch_fetch_failure():
    connector = _FakeAlgoliaConnector(
        batches=["Summer 2026", "Winter 2012"],
        hits_by_batch={"Summer 2026": [{"id": 1}]},
        errors={"Winter 2012": RuntimeError("simulated timeout")},
    )

    try:
        yc.YcDirectoryAdapter(algolia=connector).fetch()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "simulated timeout" in str(exc)


def test_fetch_logs_warning_when_total_hit_count_does_not_match_records(caplog):
    connector = _FakeAlgoliaConnector(
        batches=["Summer 2026"],
        hits_by_batch={"Summer 2026": [{"id": 531}]},
        total=6204,
    )

    with caplog.at_level(logging.WARNING, logger=yc.logger.name):
        yc.YcDirectoryAdapter(algolia=connector).fetch()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "1" in warnings[0].getMessage()
    assert "6204" in warnings[0].getMessage()


def test_fetch_does_not_log_warning_when_total_hit_count_matches_records(caplog):
    connector = _FakeAlgoliaConnector(
        batches=["Summer 2026"],
        hits_by_batch={"Summer 2026": [{"id": 531}]},
        total=1,
    )

    with caplog.at_level(logging.WARNING, logger=yc.logger.name):
        yc.YcDirectoryAdapter(algolia=connector).fetch()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == []
