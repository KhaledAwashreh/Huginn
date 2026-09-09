"""Postgres-backed StatePort: a thin read against bronze.api_ingest for
the last stored content_hash of a (source, stable_id) pair. See
architecture document section 4.1 point 4 (content-hash watermark) and
section 5 (StatePort's role in the ingestion ports diagram). ADR-0005:
logging required from day one.

Shares its lookup query with huginn.bronze.api_ingest_store (Jira KAN-32):
RawStorePort's write path and StatePort's read both need exactly the
"stored content_hash for (source, stable_id)" query against the same
table. See this plan's (Jira KAN-33) Global Constraint 2 for why this
module imports build_lookup_query rather than duplicating it.
"""

from __future__ import annotations

import logging

import psycopg

from huginn.bronze.api_ingest_store import build_lookup_query

logger = logging.getLogger(__name__)


class PostgresApiIngestState:
    """`StatePort` implementation against `bronze.api_ingest` only. See
    architecture document section 4.1 and section 5, and this plan's
    Global Constraint 2 (shared lookup query) and Constraint 4 (DEBUG-level
    per-call logging).
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def last_hash(self, source: str, stable_id: str) -> str | None:
        """See huginn.ingestion.ports.StatePort.last_hash."""
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(*build_lookup_query(source, stable_id))
            row = cur.fetchone()

        result = row[0] if row else None
        logger.debug(
            "bronze.api_ingest lookup source=%s stable_id=%s: %s",
            source,
            stable_id,
            "hit" if result is not None else "miss",
        )
        return result
