"""PostgreSQL persistence for source lifecycle observations; see docs/architecture.md §4.2."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from huginn.elt.silver.context.models import SourceExtraction, SourceName
from huginn.elt.silver.context.repository import (
    canonical_payload_sha256,
    validate_record,
)
from huginn.elt.silver.context.runner import PARSER_VERSIONS
from huginn.elt.silver.currentness.models import (
    POLICY_VERSION,
    LifecycleFacts,
    LifecycleInput,
    ReconcileResult,
)

_BRONZE_TABLES: dict[SourceName, str] = {
    "hn": "bronze.api_ingest",
    "yc": "bronze.api_ingest",
    "eu_startups": "bronze.web_scrape_ingest",
}
_MAX_STATEMENT_TIMEOUT_MS = 600_000


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


def _context_version(source: SourceName) -> str:
    return PARSER_VERSIONS[source]


class PostgresLifecycleRepository:
    """Read current lifecycle inputs and atomically append reconciled observations."""

    def __init__(
        self,
        database_url: str,
        statement_timeout_ms: int = 30_000,
        *,
        connect: Callable[..., object] | None = None,
    ) -> None:
        if (
            isinstance(statement_timeout_ms, bool)
            or not isinstance(statement_timeout_ms, int)
            or not 0 < statement_timeout_ms <= _MAX_STATEMENT_TIMEOUT_MS
        ):
            raise ValueError(
                "statement_timeout_ms must be an integer from 1 through "
                f"{_MAX_STATEMENT_TIMEOUT_MS}"
            )
        self._database_url = database_url
        self._connect = connect
        self._statement_timeout_ms = statement_timeout_ms

    def _connection(self):
        if self._connect is None:
            return psycopg.connect(self._database_url, connect_timeout=5)
        return self._connect(self._database_url)

    def _set_statement_timeout(self, connection) -> None:
        connection.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (f"{self._statement_timeout_ms}ms",),
        )

    def read_inputs(
        self, source: SourceName, limit: int | None = None
    ) -> tuple[LifecycleInput, ...]:
        if source not in _BRONZE_TABLES:
            raise ValueError(f"unsupported source: {source}")
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError("limit must be a positive integer")
        table = _BRONZE_TABLES[source]
        limit_clause = " LIMIT %s" if limit is not None else ""
        params: tuple[object, ...] = (source,)
        if limit is not None:
            params += (limit,)
        query = f"""SELECT b.stable_id, b.payload,
                           md5(b.payload::text) AS raw_token,
                           md5(jsonb_build_array(r.resolved_company_key,
                                                 r.key_derivation)::text)
                               AS resolution_token,
                           r.resolved_company_key, r.key_derivation, c.id,
                           b.fetched_at, b.last_checked_at
                    FROM {table} AS b
                    LEFT JOIN silver.resolved_signals AS r
                      ON r.source = b.source AND r.source_stable_id = b.stable_id
                    LEFT JOIN gold.company AS c
                      ON r.key_derivation = 'domain_normalized'
                     AND c.domain = r.resolved_company_key
                    WHERE b.source = %s
                    ORDER BY b.stable_id{limit_clause}"""
        with self._connection() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            self._set_statement_timeout(connection)
            rows = connection.execute(query, params).fetchall()
        return tuple(
            LifecycleInput(
                source=source,
                stable_id=row[0],
                payload=cast(dict[str, object], row[1]),
                raw_token=row[2],
                resolution_token=row[3],
                resolved_company_key=row[4],
                key_derivation=row[5],
                company_id=row[6],
                fetched_at=row[7],
                last_checked_at=row[8],
            )
            for row in rows
        )

    def reconcile(self, item: LifecycleInput, facts: LifecycleFacts) -> ReconcileResult:
        """Append a new current observation only when locked inputs still match."""
        table = _BRONZE_TABLES[item.source]
        context_version = _context_version(item.source)
        with self._connection() as connection, connection.transaction():
            self._set_statement_timeout(connection)
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"{item.source}\x1f{item.stable_id}",),
            )
            bronze = connection.execute(
                f"""SELECT payload, md5(payload::text), fetched_at, last_checked_at
                    FROM {table} WHERE source = %s AND stable_id = %s FOR SHARE""",
                (item.source, item.stable_id),
            ).fetchone()
            if bronze is None:
                return ReconcileResult("stale", None)

            resolution = connection.execute(
                """SELECT resolved_company_key, key_derivation,
                          md5(jsonb_build_array(resolved_company_key,
                                                key_derivation)::text)
                   FROM silver.resolved_signals
                   WHERE source = %s AND source_stable_id = %s FOR SHARE""",
                (item.source, item.stable_id),
            ).fetchone()
            resolved_key, derivation, resolution_token = (
                (
                    None,
                    None,
                    connection.execute(
                        "SELECT md5(jsonb_build_array(NULL::text, NULL::text)::text)"
                    ).fetchone()[0],
                )
                if resolution is None
                else resolution
            )
            company_id = None
            if derivation == "domain_normalized" and resolved_key is not None:
                company = connection.execute(
                    "SELECT id FROM gold.company WHERE domain = %s FOR SHARE",
                    (resolved_key,),
                ).fetchone()
                if company is not None:
                    company_id = company[0]

            raw_token = bronze[1]
            if (
                raw_token != item.raw_token
                or resolution_token != item.resolution_token
                or resolved_key != item.resolved_company_key
                or derivation != item.key_derivation
                or company_id != item.company_id
            ):
                return ReconcileResult("stale", None)

            current = connection.execute(
                """SELECT o.id, o.raw_token, o.resolution_token, o.company_id,
                          o.policy_version, o.context_version
                   FROM silver.source_currentness AS p
                   JOIN silver.source_lifecycle_observation AS o
                     ON o.source = p.source AND o.stable_id = p.stable_id
                    AND o.id = p.current_observation_id
                   WHERE p.source = %s AND p.stable_id = %s FOR UPDATE OF p""",
                (item.source, item.stable_id),
            ).fetchone()
            signature = (
                item.raw_token,
                item.resolution_token,
                item.company_id,
                POLICY_VERSION,
                context_version,
            )
            if current is not None and tuple(current[1:]) == signature:
                connection.execute(
                    """UPDATE silver.source_currentness
                       SET last_reconciled_at = now()
                       WHERE source = %s AND stable_id = %s""",
                    (item.source, item.stable_id),
                )
                return ReconcileResult("unchanged", current[0])

            snapshot_id = self._ensure_snapshot(
                connection, item, facts.context, context_version
            )
            inserted = connection.execute(
                """INSERT INTO silver.source_lifecycle_observation
                    (source, stable_id, raw_token, resolution_token, policy_version,
                     context_version, snapshot_id, listing_state, hiring_state,
                     identity_state, reason, explicit_domain, resolved_company_key,
                     key_derivation, company_id, occurred_at, bronze_fetched_at,
                     bronze_last_checked_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    item.source,
                    item.stable_id,
                    item.raw_token,
                    item.resolution_token,
                    POLICY_VERSION,
                    context_version,
                    snapshot_id,
                    facts.listing_state,
                    facts.hiring_state,
                    facts.identity_state,
                    facts.reason,
                    facts.explicit_domain,
                    item.resolved_company_key,
                    item.key_derivation,
                    item.company_id,
                    facts.occurred_at,
                    bronze[2],
                    bronze[3],
                ),
            ).fetchone()
            observation_id = cast(UUID, inserted[0])
            connection.execute(
                """INSERT INTO silver.source_currentness
                    (source, stable_id, current_observation_id)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (source, stable_id) DO UPDATE
                   SET current_observation_id = EXCLUDED.current_observation_id,
                       last_reconciled_at = now()""",
                (item.source, item.stable_id, observation_id),
            )
            return ReconcileResult("created", observation_id)

    def _ensure_snapshot(
        self,
        connection,
        item: LifecycleInput,
        extraction: SourceExtraction,
        parser_version: str,
    ) -> UUID | None:
        status, _reason = validate_record(item.source, item.stable_id, extraction)
        if status != "captured":
            return None
        payload_sha256 = canonical_payload_sha256(item.payload)
        header_start, header_end = (
            (None, None) if extraction.header_span is None else extraction.header_span
        )
        body_start, body_end = (
            (None, None) if extraction.body_span is None else extraction.body_span
        )
        inserted = connection.execute(
            """INSERT INTO silver.source_context_snapshot
                (source, stable_id, source_url, payload_sha256, parser_version,
                 normalized_text, header_start, header_end, body_start, body_end,
                 source_fields, source_times)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (source, stable_id, payload_sha256, parser_version)
               DO NOTHING RETURNING id""",
            (
                item.source,
                item.stable_id,
                extraction.source_url,
                payload_sha256,
                parser_version,
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
            return cast(UUID, inserted[0])
        row = connection.execute(
            """SELECT id FROM silver.source_context_snapshot
               WHERE source = %s AND stable_id = %s AND payload_sha256 = %s
                 AND parser_version = %s""",
            (item.source, item.stable_id, payload_sha256, parser_version),
        ).fetchone()
        return cast(UUID, row[0])
