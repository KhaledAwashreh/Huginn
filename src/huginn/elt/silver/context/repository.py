"""PostgreSQL persistence for immutable source-context snapshots and runs."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast

import psycopg
from psycopg.types.json import Jsonb

from huginn.elt.silver.context.models import (
    OutcomeStatus,
    SourceExtraction,
    SourceName,
)

_BRONZE_TABLES: dict[SourceName, str] = {
    "hn": "bronze.api_ingest",
    "yc": "bronze.api_ingest",
    "eu_startups": "bronze.web_scrape_ingest",
}
_STAGING_TABLES: dict[SourceName, str] = {
    "hn": "silver.hn_postings",
    "yc": "silver.yc_listings",
    "eu_startups": "silver.eu_startups_listings",
}


@dataclass(frozen=True)
class BronzeInput:
    source: SourceName
    stable_id: str
    payload: dict[str, object]
    fetched_at: datetime
    last_checked_at: datetime


@dataclass(frozen=True)
class AuditSnapshot:
    inputs: tuple[BronzeInput, ...]
    available_count: int
    coverage_counts: dict[str, int]
    downstream_by_stable_id: dict[str, dict[str, object]]


@dataclass(frozen=True)
class ContextRecord:
    stable_id: str
    payload: dict[str, object]
    extraction: SourceExtraction
    observation: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextRun:
    source: SourceName
    parser_version: str
    input_fingerprint: str
    records: tuple[ContextRecord, ...]
    mode: Literal["capture"] = "capture"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistRunResult:
    run_id: uuid.UUID
    input_count: int
    captured_count: int
    excluded_count: int
    failed_count: int
    status: Literal["complete", "partial", "failed"]


def canonical_payload_sha256(payload: Mapping[str, object]) -> str:
    """Hash full payload JSON, independent of mapping insertion order."""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _jsonb(value: Mapping[str, object]) -> Jsonb:
    return Jsonb(_json_safe(value))


def _span_values(span: tuple[int, int] | None) -> tuple[int | None, int | None]:
    return (None, None) if span is None else span


def validate_record(
    source: SourceName, stable_id: str, extraction: SourceExtraction
) -> tuple[OutcomeStatus, str | None]:
    if extraction.source != source:
        return "failed", "normalized source does not match run source"
    if extraction.stable_id is not None and extraction.stable_id != stable_id:
        return "failed", "normalized stable ID does not match Bronze stable ID"
    if extraction.status == "captured":
        if extraction.stable_id != stable_id:
            return "failed", "normalized stable ID does not match Bronze stable ID"
        if (
            (
                extraction.normalized_text is None
                or not extraction.normalized_text.strip()
            )
            and not extraction.source_fields
            and not extraction.source_times
        ):
            return "failed", "captured extraction has no text or source observations"
    return extraction.status, extraction.reason


class SourceContextRepository:
    """Reads current Bronze inputs and stores additive context records.

    Reads use a read-only transaction by default. Snapshot+outcome insertion is
    one transaction per record; a run row is committed first, so an interrupted
    capture remains visible with status ``running`` and its selected input count.
    """

    def __init__(
        self,
        database_url: str,
        *,
        connect: Callable[..., object] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connect = connect or psycopg.connect

    def _connection(self):
        return self._connect(self._database_url)

    def read_inputs(
        self,
        source: SourceName,
        limit: int | None = None,
        *,
        read_only: bool = True,
    ) -> list[BronzeInput]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be a positive integer")
        table = _BRONZE_TABLES[source]
        query = (
            f"SELECT source, stable_id, payload, fetched_at, last_checked_at "
            f"FROM {table} WHERE source = %s "
            "ORDER BY md5(stable_id), stable_id"
        )
        params: tuple[object, ...] = (source,)
        if limit is not None:
            query += " LIMIT %s"
            params += (limit,)

        with self._connection() as connection, connection.transaction():
            if read_only:
                connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            rows = connection.execute(query, params).fetchall()
        return [
            BronzeInput(
                source=cast(SourceName, row[0]),
                stable_id=row[1],
                payload=row[2],
                fetched_at=row[3],
                last_checked_at=row[4],
            )
            for row in rows
        ]

    def count_inputs(self, source: SourceName) -> int:
        table = _BRONZE_TABLES[source]
        with self._connection() as connection, connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            return connection.execute(
                f"SELECT count(*) FROM {table} WHERE source = %s", (source,)
            ).fetchone()[0]

    def read_audit_snapshot(
        self, source: SourceName, limit: int | None = None
    ) -> AuditSnapshot:
        """Read Bronze, coverage totals, and matched projections consistently."""
        if limit is not None and limit <= 0:
            raise ValueError("limit must be a positive integer")
        bronze_table = _BRONZE_TABLES[source]
        staging_table = _STAGING_TABLES[source]
        inputs: list[BronzeInput] = []
        downstream: dict[str, dict[str, object]] = {}
        with self._connection() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.execute("SET LOCAL statement_timeout = '5s'")
            available_count = connection.execute(
                f"SELECT count(*) FROM {bronze_table} WHERE source = %s", (source,)
            ).fetchone()[0]
            query = (
                f"SELECT source, stable_id, payload, fetched_at, last_checked_at "
                f"FROM {bronze_table} WHERE source = %s "
                "ORDER BY md5(stable_id), stable_id"
            )
            params: tuple[object, ...] = (source,)
            if limit is not None:
                query += " LIMIT %s"
                params += (limit,)
            rows = connection.execute(query, params).fetchall()
            inputs = [
                BronzeInput(
                    source=cast(SourceName, row[0]),
                    stable_id=row[1],
                    payload=row[2],
                    fetched_at=row[3],
                    last_checked_at=row[4],
                )
                for row in rows
            ]
            staging_count = connection.execute(
                f"SELECT count(*) FROM {staging_table}"
            ).fetchone()[0]
            resolved_count = connection.execute(
                "SELECT count(*) FROM silver.resolved_signals "
                "WHERE source = %s AND key_derivation <> 'unresolved'",
                (source,),
            ).fetchone()[0]
            unresolved_count = connection.execute(
                "SELECT count(*) FROM silver.resolved_signals "
                "WHERE source = %s AND key_derivation = 'unresolved'",
                (source,),
            ).fetchone()[0]
            gold_count = connection.execute(
                "SELECT count(*) FROM gold.company_signal WHERE source = %s",
                (source,),
            ).fetchone()[0]
            stable_ids = [item.stable_id for item in inputs]
            downstream = {
                stable_id: {
                    "silver_staging_description": None,
                    "silver_resolved_description": None,
                    "silver_key_derivation": None,
                    "gold_description": None,
                }
                for stable_id in stable_ids
            }
            if stable_ids:
                for row in connection.execute(
                    f"SELECT stable_id, description FROM {staging_table} "
                    "WHERE stable_id = ANY(%s)",
                    (stable_ids,),
                ).fetchall():
                    downstream[row[0]]["silver_staging_description"] = row[1]
                for row in connection.execute(
                    "SELECT source_stable_id, description, key_derivation "
                    "FROM silver.resolved_signals "
                    "WHERE source = %s AND source_stable_id = ANY(%s)",
                    (source, stable_ids),
                ).fetchall():
                    downstream[row[0]]["silver_resolved_description"] = row[1]
                    downstream[row[0]]["silver_key_derivation"] = row[2]
                for row in connection.execute(
                    "SELECT source_stable_id, description FROM gold.company_signal "
                    "WHERE source = %s AND source_stable_id = ANY(%s)",
                    (source, stable_ids),
                ).fetchall():
                    downstream[row[0]]["gold_description"] = row[1]

        return AuditSnapshot(
            inputs=tuple(inputs),
            available_count=available_count,
            coverage_counts={
                "bronze": available_count,
                "silver_staging": staging_count,
                "silver_resolved": resolved_count,
                "silver_unresolved": unresolved_count,
                "gold_signals": gold_count,
            },
            downstream_by_stable_id=downstream,
        )

    def coverage_counts(self, source: SourceName) -> dict[str, int]:
        staging_table = _STAGING_TABLES[source]
        bronze_table = _BRONZE_TABLES[source]
        with self._connection() as connection, connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            bronze = connection.execute(
                f"SELECT count(*) FROM {bronze_table} WHERE source = %s", (source,)
            ).fetchone()[0]
            staging = connection.execute(
                f"SELECT count(*) FROM {staging_table}"
            ).fetchone()[0]
            resolved = connection.execute(
                "SELECT count(*) FROM silver.resolved_signals "
                "WHERE source = %s AND key_derivation <> 'unresolved'",
                (source,),
            ).fetchone()[0]
            unresolved = connection.execute(
                "SELECT count(*) FROM silver.resolved_signals "
                "WHERE source = %s AND key_derivation = 'unresolved'",
                (source,),
            ).fetchone()[0]
            gold = connection.execute(
                "SELECT count(*) FROM gold.company_signal WHERE source = %s",
                (source,),
            ).fetchone()[0]
        return {
            "bronze": bronze,
            "silver_staging": staging,
            "silver_resolved": resolved,
            "silver_unresolved": unresolved,
            "gold_signals": gold,
        }

    def persist_run(self, run: ContextRun) -> PersistRunResult:
        if run.mode != "capture":
            raise ValueError("only capture runs may be persisted")
        if re.fullmatch(r"[0-9a-f]{64}", run.input_fingerprint) is None:
            raise ValueError("input_fingerprint must be a SHA-256 hex digest")
        run_id = uuid.uuid4()
        with self._connection() as connection, connection.transaction():
            connection.execute(
                """INSERT INTO silver.source_context_run
                        (id, source, mode, parser_version, input_fingerprint,
                         status, total_inputs, run_metadata)
                       VALUES (%s, %s, %s, %s, %s, 'running', %s, %s)""",
                (
                    run_id,
                    run.source,
                    run.mode,
                    run.parser_version,
                    run.input_fingerprint,
                    len(run.records),
                    _jsonb(run.metadata),
                ),
            )

        captured = excluded = failed = 0
        try:
            for record in run.records:
                extraction_status, reason = validate_record(
                    run.source, record.stable_id, record.extraction
                )
                payload_hash = canonical_payload_sha256(record.payload)
                snapshot_id: uuid.UUID | None = None

                with self._connection() as connection, connection.transaction():
                    if extraction_status == "captured":
                        extraction = record.extraction
                        header_start, header_end = _span_values(extraction.header_span)
                        body_start, body_end = _span_values(extraction.body_span)
                        inserted = connection.execute(
                            """INSERT INTO silver.source_context_snapshot
                                (source, stable_id, source_url, payload_sha256,
                                 parser_version, normalized_text, header_start,
                                 header_end, body_start, body_end, source_fields,
                                 source_times)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (source, stable_id, payload_sha256, parser_version)
                               DO NOTHING RETURNING id""",
                            (
                                run.source,
                                record.stable_id,
                                extraction.source_url,
                                payload_hash,
                                run.parser_version,
                                extraction.normalized_text,
                                header_start,
                                header_end,
                                body_start,
                                body_end,
                                _jsonb(extraction.source_fields),
                                _jsonb(extraction.source_times),
                            ),
                        ).fetchone()
                        if inserted is not None:
                            snapshot_id = inserted[0]
                        else:
                            snapshot_id = connection.execute(
                                """SELECT id FROM silver.source_context_snapshot
                                   WHERE source = %s AND stable_id = %s
                                     AND payload_sha256 = %s AND parser_version = %s""",
                                (
                                    run.source,
                                    record.stable_id,
                                    payload_hash,
                                    run.parser_version,
                                ),
                            ).fetchone()[0]

                    connection.execute(
                        """INSERT INTO silver.source_context_outcome
                            (run_id, source, stable_id, payload_sha256, status,
                             reason, snapshot_id, observation_metadata)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            run_id,
                            run.source,
                            record.stable_id,
                            payload_hash,
                            extraction_status,
                            reason,
                            snapshot_id,
                            _jsonb(
                                {
                                    "bronze_observation": record.observation,
                                    "source_times": record.extraction.source_times,
                                }
                            ),
                        ),
                    )

                if extraction_status == "captured":
                    captured += 1
                elif extraction_status == "excluded":
                    excluded += 1
                else:
                    failed += 1

            status: Literal["complete", "partial", "failed"] = (
                "complete"
                if failed == 0
                else "failed"
                if captured + excluded == 0
                else "partial"
            )
            with self._connection() as connection, connection.transaction():
                connection.execute(
                    """UPDATE silver.source_context_run
                           SET status = %s, captured_count = %s, excluded_count = %s,
                               failed_count = %s, finished_at = %s
                           WHERE id = %s""",
                    (
                        status,
                        captured,
                        excluded,
                        failed,
                        datetime.now(UTC),
                        run_id,
                    ),
                )
        except Exception as exc:
            try:
                with self._connection() as connection, connection.transaction():
                    connection.execute(
                        """UPDATE silver.source_context_run
                           SET status = 'interrupted', captured_count = %s,
                               excluded_count = %s, failed_count = %s,
                               finished_at = %s,
                               run_metadata = run_metadata ||
                                   jsonb_build_object('interruption_type', %s::text)
                           WHERE id = %s""",
                        (
                            captured,
                            excluded,
                            failed,
                            datetime.now(UTC),
                            type(exc).__name__,
                            run_id,
                        ),
                    )
            except Exception as finalize_error:
                exc.add_note(
                    "interrupted-run finalization failed: "
                    f"{type(finalize_error).__name__}"
                )
            raise
        return PersistRunResult(
            run_id=run_id,
            input_count=len(run.records),
            captured_count=captured,
            excluded_count=excluded,
            failed_count=failed,
            status=status,
        )
