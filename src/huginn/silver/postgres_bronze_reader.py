"""Postgres-backed `BronzeReaderPort`. See huginn.silver.ports and
architecture document section 4.1. Shared by every staging loader: the
read side of bronze.api_ingest is identical regardless of source.
"""

from __future__ import annotations

import psycopg

_SELECT_SQL = "SELECT payload FROM bronze.api_ingest WHERE source = %s"


class PostgresBronzeReader:
    """`BronzeReaderPort` implementation against bronze.api_ingest."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def read(self, source: str) -> list[dict]:
        """Return every current payload for `source`."""
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(_SELECT_SQL, (source,))
            return [row[0] for row in cur.fetchall()]
