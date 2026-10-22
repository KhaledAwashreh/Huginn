from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from huginn.elt.silver.context.models import SourceExtraction
from huginn.elt.silver.context.repository import (
    ContextRecord,
    ContextRun,
    SourceContextRepository,
    canonical_payload_sha256,
    validate_record,
)


def test_payload_digest_uses_canonical_full_payload_json() -> None:
    first = {"html": "body", "url": "https://example.test", "lastmod": "old"}
    reordered = {"lastmod": "old", "url": "https://example.test", "html": "body"}

    assert canonical_payload_sha256(first) == canonical_payload_sha256(reordered)
    assert (
        canonical_payload_sha256(first)
        == hashlib.sha256(
            json.dumps(
                first, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    assert canonical_payload_sha256(
        {**first, "html": "new"}
    ) != canonical_payload_sha256(first)


def test_validate_record_is_shared_pure_capture_classification() -> None:
    matching = _captured("company-a", "A description")
    mismatched = _captured("company-b", "B description")

    assert validate_record("eu_startups", "company-a", matching) == (
        "captured",
        None,
    )
    assert validate_record("eu_startups", "company-a", mismatched) == (
        "failed",
        "normalized stable ID does not match Bronze stable ID",
    )
    assert validate_record("yc", "company-a", matching) == (
        "failed",
        "normalized source does not match run source",
    )


def _captured(stable_id: str, description: str) -> SourceExtraction:
    return SourceExtraction(
        source="eu_startups",
        stable_id=stable_id,
        status="captured",
        source_url=f"https://www.eu-startups.com/directory/{stable_id}/",
        normalized_text=f"Listing: {stable_id}\nDescription: {description}",
        source_fields={"description": description},
        source_times={"lastmod": "2026-01-01T00:00:00+00:00"},
    )


def _run(
    stable_id: str,
    payload: dict[str, object],
    description: str,
    parser_version: str = "1",
) -> ContextRun:
    return ContextRun(
        source="eu_startups",
        parser_version=parser_version,
        input_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        records=(
            ContextRecord(
                stable_id=stable_id,
                payload=payload,
                extraction=_captured(stable_id, description),
                observation={
                    "fetched_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "last_checked_at": datetime(2026, 1, 2, tzinfo=UTC),
                },
            ),
        ),
    )


def test_capture_reuses_identical_snapshot_and_keeps_changed_payload_versions(
    integration_database_url: str,
) -> None:
    stable_id = f"ctx-{uuid.uuid4().hex}"
    legacy_id = f"legacy-{uuid.uuid4().hex}"
    repository = SourceContextRepository(integration_database_url)
    payload = {
        "url": f"https://www.eu-startups.com/directory/{stable_id}/",
        "html": "old",
    }

    with psycopg.connect(integration_database_url) as connection:
        connection.execute(
            "INSERT INTO silver.eu_startups_listings "
            "(stable_id, company_name_raw, signal_type, description) "
            "VALUES (%s, 'Legacy sentinel', 'other', 'Keep this description')",
            (legacy_id,),
        )

    first = repository.persist_run(_run(stable_id, payload, "old"))
    repeated = repository.persist_run(_run(stable_id, payload, "old"))
    changed = repository.persist_run(_run(stable_id, {**payload, "html": "new"}, "new"))
    new_parser = repository.persist_run(_run(stable_id, payload, "old", "2"))

    try:
        assert (
            first.status
            == repeated.status
            == changed.status
            == new_parser.status
            == "complete"
        )
        assert (
            first.captured_count
            == repeated.captured_count
            == changed.captured_count
            == new_parser.captured_count
            == 1
        )
        with psycopg.connect(integration_database_url) as connection:
            snapshots = connection.execute(
                "SELECT payload_sha256, parser_version, normalized_text "
                "FROM silver.source_context_snapshot "
                "WHERE source = 'eu_startups' AND stable_id = %s "
                "ORDER BY parser_version, payload_sha256",
                (stable_id,),
            ).fetchall()
            assert len(snapshots) == 3
            assert {(row[1], row[2]) for row in snapshots} == {
                ("1", f"Listing: {stable_id}\nDescription: old"),
                ("2", f"Listing: {stable_id}\nDescription: old"),
                ("1", f"Listing: {stable_id}\nDescription: new"),
            }
            assert {row[2] for row in snapshots} == {
                f"Listing: {stable_id}\nDescription: old",
                f"Listing: {stable_id}\nDescription: new",
            }
            assert (
                connection.execute(
                    "SELECT count(DISTINCT snapshot_id) FROM silver.source_context_outcome "
                    "WHERE source = 'eu_startups' AND stable_id = %s",
                    (stable_id,),
                ).fetchone()[0]
                == 3
            )
            assert connection.execute(
                "SELECT company_name_raw, description "
                "FROM silver.eu_startups_listings WHERE stable_id = %s",
                (legacy_id,),
            ).fetchone() == ("Legacy sentinel", "Keep this description")
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM silver.source_context_run WHERE source = 'eu_startups' "
                "AND id IN (SELECT run_id FROM silver.source_context_outcome "
                "WHERE source = 'eu_startups' AND stable_id = %s)",
                (stable_id,),
            )
            connection.execute(
                "DELETE FROM silver.source_context_snapshot WHERE source = 'eu_startups' "
                "AND stable_id = %s",
                (stable_id,),
            )
            connection.execute(
                "DELETE FROM silver.eu_startups_listings WHERE stable_id = %s",
                (legacy_id,),
            )


def test_capture_keeps_status_only_source_observation_without_text(
    integration_database_url: str,
) -> None:
    stable_id = f"yc-status-{uuid.uuid4().hex}"
    extraction = SourceExtraction(
        source="yc",
        stable_id=stable_id,
        status="captured",
        normalized_text=None,
        source_fields={
            "company_status": "Inactive",
            "is_hiring": False,
            "team_size": 0,
        },
    )
    record = ContextRecord(
        stable_id=stable_id,
        payload={"id": stable_id, "status": "Inactive"},
        extraction=extraction,
    )
    run = ContextRun(
        source="yc",
        parser_version="1",
        input_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        records=(record,),
    )

    result = SourceContextRepository(integration_database_url).persist_run(run)

    try:
        assert result.status == "complete"
        assert result.captured_count == 1
        with psycopg.connect(integration_database_url) as connection:
            assert connection.execute(
                "SELECT normalized_text, source_fields "
                "FROM silver.source_context_snapshot WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            ).fetchone() == (
                None,
                {"company_status": "Inactive", "is_hiring": False, "team_size": 0},
            )
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM silver.source_context_run WHERE id = %s", (result.run_id,)
            )
            connection.execute(
                "DELETE FROM silver.source_context_snapshot WHERE source = 'yc' "
                "AND stable_id = %s",
                (stable_id,),
            )


def test_run_records_failed_input_without_placeholder_snapshot(
    integration_database_url: str,
) -> None:
    stable_id = f"failed-{uuid.uuid4().hex}"
    record = ContextRecord(
        stable_id=stable_id,
        payload={"raw": "malformed"},
        extraction=SourceExtraction(
            source="eu_startups",
            stable_id=stable_id,
            status="failed",
            reason="bad page",
        ),
    )
    run = ContextRun(
        source="eu_startups",
        parser_version="1",
        input_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        records=(record,),
    )

    result = SourceContextRepository(integration_database_url).persist_run(run)

    try:
        assert result.status == "failed"
        assert result.failed_count == 1
        with psycopg.connect(integration_database_url) as connection:
            assert connection.execute(
                "SELECT status, reason, snapshot_id "
                "FROM silver.source_context_outcome WHERE run_id = %s",
                (result.run_id,),
            ).fetchone() == ("failed", "bad page", None)
            assert (
                connection.execute(
                    "SELECT count(*) FROM silver.source_context_snapshot "
                    "WHERE source = 'eu_startups' AND stable_id = %s",
                    (stable_id,),
                ).fetchone()[0]
                == 0
            )
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM silver.source_context_run WHERE id = %s", (result.run_id,)
            )


def test_excluded_source_time_is_preserved_without_snapshot(
    integration_database_url: str,
) -> None:
    stable_id = f"excluded-hn-{uuid.uuid4().hex}"
    event_time = datetime(2024, 2, 3, 4, 5, tzinfo=UTC)
    record = ContextRecord(
        stable_id=stable_id,
        payload={"id": stable_id, "dead": True},
        extraction=SourceExtraction(
            source="hn",
            stable_id=stable_id,
            status="excluded",
            reason="dead item",
            source_times={"time": event_time},
        ),
        observation={"last_checked_at": datetime(2026, 1, 2, tzinfo=UTC)},
    )
    run = ContextRun(
        source="hn",
        parser_version="1",
        input_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        records=(record,),
    )

    result = SourceContextRepository(integration_database_url).persist_run(run)

    try:
        with psycopg.connect(integration_database_url) as connection:
            assert connection.execute(
                "SELECT status, snapshot_id, observation_metadata "
                "FROM silver.source_context_outcome WHERE run_id = %s",
                (result.run_id,),
            ).fetchone() == (
                "excluded",
                None,
                {
                    "bronze_observation": {
                        "last_checked_at": "2026-01-02T00:00:00+00:00"
                    },
                    "source_times": {"time": "2024-02-03T04:05:00+00:00"},
                },
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM silver.source_context_snapshot "
                    "WHERE source = 'hn' AND stable_id = %s",
                    (stable_id,),
                ).fetchone()[0]
                == 0
            )
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM silver.source_context_run WHERE id = %s", (result.run_id,)
            )


def test_source_and_stable_id_mismatch_become_failed_outcome(
    integration_database_url: str,
) -> None:
    stable_id = f"mismatch-{uuid.uuid4().hex}"
    extraction = _captured(f"{stable_id}-wrong", "must not be attached")
    record = ContextRecord(
        stable_id=stable_id,
        payload={"id": stable_id},
        extraction=extraction,
    )
    run = ContextRun(
        source="eu_startups",
        parser_version="1",
        input_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        records=(record,),
    )
    result = SourceContextRepository(integration_database_url).persist_run(run)

    try:
        assert result.status == "failed"
        with psycopg.connect(integration_database_url) as connection:
            assert connection.execute(
                "SELECT status, reason, snapshot_id "
                "FROM silver.source_context_outcome WHERE run_id = %s",
                (result.run_id,),
            ).fetchone() == (
                "failed",
                "normalized stable ID does not match Bronze stable ID",
                None,
            )
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM silver.source_context_run WHERE id = %s", (result.run_id,)
            )


def test_input_fingerprint_must_be_64_lowercase_hex_characters() -> None:
    stable_id = f"fingerprint-{uuid.uuid4().hex}"
    bad_run = ContextRun(
        source="eu_startups",
        parser_version="1",
        input_fingerprint="g" * 64,
        records=(
            ContextRecord(
                stable_id=stable_id,
                payload={"id": stable_id},
                extraction=_captured(stable_id, "text"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="SHA-256 hex digest"):
        SourceContextRepository("unused").persist_run(bad_run)


def test_statement_timeout_is_validated_and_applied_to_all_read_paths() -> None:
    for value in (0, -1, 600_001, 1.5, True):
        with pytest.raises(ValueError, match="statement_timeout_ms"):
            SourceContextRepository("unused", statement_timeout_ms=value)

    connection = _RecordingConnection()
    repository = SourceContextRepository(
        "unused", connect=lambda _: connection, statement_timeout_ms=1234
    )
    repository.read_inputs("eu_startups", limit=1)
    repository.count_inputs("eu_startups")
    repository.read_audit_snapshot("eu_startups", limit=1)
    repository.coverage_counts("eu_startups")

    timeout_calls = [
        call for call in connection.calls if "set_config('statement_timeout'" in call[0]
    ]
    assert len(timeout_calls) == 4
    assert all(call[1] == ("1234ms",) for call in timeout_calls)
    repeatable_read_calls = [
        call
        for call in connection.calls
        if "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY" in call[0]
    ]
    assert len(repeatable_read_calls) == 2


class _RecordingResult:
    def __init__(self, rows=()):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else (0,)


class _RecordingConnection:
    def __init__(self):
        self.calls = []
        self.transaction_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def transaction(self):
        from contextlib import nullcontext

        self.transaction_count += 1
        return nullcontext()

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _RecordingResult()


def test_persist_run_uses_one_processing_connection_for_record_transactions() -> None:
    connections = []

    def connect(_url):
        connection = _RecordingConnection()
        connections.append(connection)
        return connection

    records = tuple(
        ContextRecord(
            stable_id=f"bounded-{index}",
            payload={"id": f"bounded-{index}"},
            extraction=_captured(f"bounded-{index}", "description"),
        )
        for index in range(3)
    )
    run = ContextRun(
        source="eu_startups",
        parser_version="1",
        input_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        records=records,
    )

    result = SourceContextRepository("unused", connect=connect).persist_run(run)

    assert result.status == "complete"
    assert len(connections) == 2  # receipt connection plus processing connection
    processing_inserts = [
        call
        for call in connections[1].calls
        if "INSERT INTO silver.source_context" in call[0]
    ]
    assert len(processing_inserts) == 6  # 3 snapshots and 3 outcomes
    assert connections[1].transaction_count == 4  # one per record plus finalization


def test_processing_connection_acquisition_failure_marks_committed_receipt_interrupted() -> (
    None
):
    receipt_connection = _RecordingConnection()
    recovery_connection = _RecordingConnection()
    connect_calls = 0
    original_error = RuntimeError("processing connection unavailable")

    def connect(_url):
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 1:
            return receipt_connection
        if connect_calls == 2:
            raise original_error
        return recovery_connection

    run = _run("connection-failure", {"id": "connection-failure"}, "description")

    with pytest.raises(
        RuntimeError, match="processing connection unavailable"
    ) as raised:
        SourceContextRepository("unused", connect=connect).persist_run(run)

    assert raised.value is original_error
    assert connect_calls == 3
    recovery_updates = [
        call
        for call in recovery_connection.calls
        if "SET status = 'interrupted'" in call[0]
    ]
    assert len(recovery_updates) == 1


def test_interrupted_run_keeps_completed_records_and_marks_partial_progress(
    integration_database_url: str,
) -> None:
    repository = SourceContextRepository(integration_database_url)
    stable_ids = [f"interrupt-{uuid.uuid4().hex}" for _ in range(2)]
    payloads = [{"url": stable_id} for stable_id in stable_ids]
    records = (
        ContextRecord(
            stable_id=stable_ids[0],
            payload=payloads[0],
            extraction=_captured(stable_ids[0], "first"),
        ),
        ContextRecord(
            stable_id=stable_ids[1],
            payload=payloads[1],
            extraction=_captured(stable_ids[1], "second"),
            observation={"unsupported": object()},
        ),
    )
    run = ContextRun(
        source="eu_startups",
        parser_version="1",
        input_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        records=records,
    )

    with pytest.raises(TypeError, match="unsupported JSON value: object") as error:
        repository.persist_run(run)
    assert not getattr(error.value, "__notes__", [])

    try:
        with psycopg.connect(integration_database_url) as connection:
            run_row = connection.execute(
                "SELECT id, status, total_inputs, captured_count, failed_count "
                "FROM silver.source_context_run WHERE input_fingerprint = %s",
                (run.input_fingerprint,),
            ).fetchone()
            assert run_row is not None
            run_id, status, total, captured, failed = run_row
            assert (status, total, captured, failed) == ("interrupted", 2, 1, 0)
            outcomes = connection.execute(
                "SELECT stable_id, status FROM silver.source_context_outcome "
                "WHERE run_id = %s ORDER BY stable_id",
                (run_id,),
            ).fetchall()
            assert outcomes == [(stable_ids[0], "captured")]
            snapshots = connection.execute(
                "SELECT stable_id FROM silver.source_context_snapshot "
                "WHERE stable_id = ANY(%s)",
                (stable_ids,),
            ).fetchall()
            assert snapshots == [(stable_ids[0],)]
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM silver.source_context_run WHERE input_fingerprint = %s",
                (run.input_fingerprint,),
            )
            connection.execute(
                "DELETE FROM silver.source_context_snapshot WHERE stable_id = ANY(%s)",
                (stable_ids,),
            )


def test_reader_orders_by_stable_id_and_keeps_observation_times_outside_payload(
    integration_database_url: str,
) -> None:
    run_id = uuid.uuid4()
    ids = [f"reader-{uuid.uuid4().hex}" for _ in range(2)]
    try:
        with psycopg.connect(integration_database_url) as connection:
            for stable_id in ids:
                connection.execute(
                    "INSERT INTO bronze.web_scrape_ingest "
                    "(source, stable_id, payload, content_hash, run_id, fetched_at, last_checked_at) "
                    "VALUES ('eu_startups', %s, %s, 'hash', %s, %s, %s)",
                    (
                        stable_id,
                        psycopg.types.json.Jsonb({"url": stable_id}),
                        run_id,
                        datetime(2026, 1, 1, tzinfo=UTC),
                        datetime(2026, 1, 2, tzinfo=UTC),
                    ),
                )
            connection.execute(
                "INSERT INTO silver.eu_startups_listings "
                "(stable_id, company_name_raw, signal_type, description) "
                "VALUES (%s, 'Reader Example', 'other', 'Staging description')",
                (ids[0],),
            )
            connection.execute(
                "INSERT INTO silver.resolved_signals "
                "(source_stable_id, source, resolved_company_key, company_name_raw, "
                "signal_type, description, key_derivation) "
                "VALUES (%s, 'eu_startups', %s, 'Reader Example', 'other', "
                "'Resolved description', 'unresolved')",
                (ids[0], f"unresolved:{ids[0]}"),
            )

        repository = SourceContextRepository(integration_database_url)
        inputs = repository.read_inputs("eu_startups")
        prefix = repository.read_inputs("eu_startups", limit=2)
        selected = [item for item in inputs if item.stable_id in ids]

        assert len(selected) == 2
        assert prefix == inputs[:2]
        assert [item.stable_id for item in selected] == sorted(
            ids,
            key=lambda stable_id: (
                hashlib.md5(stable_id.encode()).hexdigest(),
                stable_id,
            ),
        )
        assert all(item.payload == {"url": item.stable_id} for item in selected)
        assert all(
            item.fetched_at == datetime(2026, 1, 1, tzinfo=UTC) for item in selected
        )
        assert all(
            item.last_checked_at == datetime(2026, 1, 2, tzinfo=UTC)
            for item in selected
        )
        audit = repository.read_audit_snapshot("eu_startups")
        assert audit.available_count >= 2
        assert audit.coverage_counts["bronze"] == audit.available_count
        assert repository.coverage_counts("eu_startups") == audit.coverage_counts
        assert audit.downstream_by_stable_id[ids[0]] == {
            "silver_staging_description": "Staging description",
            "silver_resolved_description": "Resolved description",
            "silver_key_derivation": "unresolved",
            "gold_description": None,
        }
        assert audit.coverage_counts["silver_unresolved"] >= 1
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM silver.resolved_signals WHERE source = 'eu_startups' "
                "AND source_stable_id = ANY(%s)",
                (ids,),
            )
            connection.execute(
                "DELETE FROM silver.eu_startups_listings WHERE stable_id = ANY(%s)",
                (ids,),
            )
            connection.execute(
                "DELETE FROM bronze.web_scrape_ingest WHERE source = 'eu_startups' "
                "AND stable_id = ANY(%s)",
                (ids,),
            )


class _ReadOnlyMutationProbe:
    def __init__(self, url: str) -> None:
        self.connection = psycopg.connect(url)
        self.rejected_mutation = False
        self.observed_timeout = None

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.connection.__exit__(exc_type, exc_value, traceback)

    def transaction(self):
        return self.connection.transaction()

    def execute(self, query: str, params=()):
        result = self.connection.execute(query, params)
        if "set_config('statement_timeout'" in query and not self.rejected_mutation:
            self.observed_timeout = self.connection.execute(
                "SHOW statement_timeout"
            ).fetchone()[0]
            self.connection.execute("SAVEPOINT read_only_mutation_probe")
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                self.connection.execute(
                    "INSERT INTO silver.source_context_run "
                    "(source, mode, parser_version, input_fingerprint) "
                    "VALUES ('yc', 'capture', 'probe', %s)",
                    ("a" * 64,),
                )
            self.connection.execute("ROLLBACK TO SAVEPOINT read_only_mutation_probe")
            self.connection.execute("RELEASE SAVEPOINT read_only_mutation_probe")
            self.rejected_mutation = True
        return result


def test_default_input_reader_rejects_mutations_in_read_only_transaction(
    integration_database_url: str,
) -> None:
    probe = _ReadOnlyMutationProbe(integration_database_url)
    repository = SourceContextRepository(
        integration_database_url, connect=lambda _: probe
    )

    repository.read_inputs("eu_startups", limit=1)

    assert probe.rejected_mutation is True
    assert probe.observed_timeout == "30s"
