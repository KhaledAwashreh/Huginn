"""Postgres-backed RawStorePort for bronze.api_ingest. See architecture
document section 4.1 point 4 (skip-on-hash-match write) and ADR-0005
(logging required from day one).

Only bronze.api_ingest is wired here (Jira KAN-32). web_scrape_ingest and
newsletter_ingest get the same write path once a mechanism using them
exists; no adapter needs it yet.
"""

from __future__ import annotations

import logging
import uuid

import psycopg
from psycopg.types.json import Jsonb

from huginn.bronze.watermark import compute_content_hash
from huginn.ingestion.ports import RawRecord

logger = logging.getLogger(__name__)

ACTION_WRITE = "write"
ACTION_SKIP = "skip"


def decide_write_action(existing_hash: str | None, new_hash: str) -> str:
    """Decide whether a record needs a write (fresh insert or
    hash-changed overwrite) or only a last_checked_at touch.

    See architecture document section 4.1 point 4 and docs/superpowers/plans/
    2026-09-08-kan-32-raw-store-port.md's Global Constraint 3: no existing row, or an existing row whose content_hash
    differs, both write; a matching hash only touches last_checked_at.
    Pure decision logic, no I/O (CLAUDE.md code standard 4).
    """
    if existing_hash is None or existing_hash != new_hash:
        return ACTION_WRITE
    return ACTION_SKIP


_LOOKUP_SQL = (
    "SELECT content_hash FROM bronze.api_ingest WHERE source = %s AND stable_id = %s"
)

_WRITE_SQL = """
    INSERT INTO bronze.api_ingest (source, stable_id, payload, content_hash, run_id)
    VALUES (%s, %s, %s, %s, %s::uuid)
    ON CONFLICT (source, stable_id) DO UPDATE
    SET payload = EXCLUDED.payload,
        content_hash = EXCLUDED.content_hash,
        run_id = EXCLUDED.run_id,
        fetched_at = now(),
        last_checked_at = now()
"""

_TOUCH_SQL = "UPDATE bronze.api_ingest SET last_checked_at = now() WHERE source = %s AND stable_id = %s"


def build_lookup_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]:
    """Parameterized SELECT for the stored content_hash of (source,
    stable_id), or no row if never seen. BEST_PRACTICES.md section 8.1:
    bind parameters only, never string-built SQL.
    """
    return _LOOKUP_SQL, (source, stable_id)


def build_write_query(
    source: str, stable_id: str, payload: dict, content_hash: str, run_id: str
) -> tuple[str, tuple[str, str, Jsonb, str, str]]:
    """Parameterized upsert: a fresh (source, stable_id) inserts, an
    existing one with a changed hash overwrites in place. See this plan's
    Global Constraint 3 for why this is an upsert, not a plain INSERT.
    """
    return _WRITE_SQL, (source, stable_id, Jsonb(payload), content_hash, run_id)


def build_touch_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]:
    """Parameterized UPDATE bumping last_checked_at only, no payload or
    content_hash change, for a hash-match skip. Architecture document
    section 4.1 point 4.
    """
    return _TOUCH_SQL, (source, stable_id)


class PostgresApiIngestStore:
    """`RawStorePort` implementation against `bronze.api_ingest` only. See
    architecture document section 4.1 point 4 and docs/superpowers/plans/
    2026-09-08-kan-32-raw-store-port.md's Global Constraint 3 (upsert semantics) and Constraint 4 (stable_fields choice).
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def write(
        self, source: str, mechanism: str, records: list[RawRecord], run_id: str
    ) -> int:
        """See huginn.ingestion.ports.RawStorePort.write. Only mechanism
        "api" is handled (Jira KAN-32 scope; see docs/superpowers/plans/
        2026-09-08-kan-32-raw-store-port.md, Global Constraint 5). Returns
        the count actually written, excluding hash-match skips.
        """
        if mechanism != "api":
            raise NotImplementedError(
                f"PostgresApiIngestStore only writes bronze.api_ingest "
                f"('api' mechanism); got mechanism={mechanism!r}. "
                f"web_scrape_ingest and newsletter_ingest are out of scope "
                f"for KAN-32."
            )

        try:
            uuid.UUID(run_id)
        except ValueError as exc:
            raise ValueError(
                f"run_id must be a valid UUID string; got {run_id!r}"
            ) from exc

        written = 0
        skipped = 0
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            for record in records:
                content_hash = compute_content_hash(
                    record.payload, sorted(record.payload.keys())
                )
                cur.execute(*build_lookup_query(source, record.stable_id))
                row = cur.fetchone()
                existing_hash = row[0] if row else None

                if decide_write_action(existing_hash, content_hash) == ACTION_WRITE:
                    cur.execute(
                        *build_write_query(
                            source,
                            record.stable_id,
                            record.payload,
                            content_hash,
                            run_id,
                        )
                    )
                    written += 1
                else:
                    cur.execute(*build_touch_query(source, record.stable_id))
                    skipped += 1

        logger.info(
            "bronze.api_ingest write source=%s run_id=%s: %d written, %d skipped",
            source,
            run_id,
            written,
            skipped,
        )
        return written
