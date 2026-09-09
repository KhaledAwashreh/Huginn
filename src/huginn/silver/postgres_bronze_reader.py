"""Postgres-backed `BronzeReaderPort`. See huginn.silver.ports and
architecture document section 4.1. Shared by every staging loader: the
read side of bronze.api_ingest is identical regardless of source.
"""

from __future__ import annotations

import psycopg

_SELECT_SQL = "SELECT payload FROM bronze.api_ingest WHERE source = %s"


class PostgresBronzeReader:
    """`BronzeReaderPort` implementation against bronze.api_ingest.

    A context manager: one connection and one cursor span the whole `with`
    block, so an orchestrator's entire call shares a single connection and
    a single transaction (see huginn.silver.ports' connection-scope note).
    `read` therefore assumes it is called between `__enter__` and
    `__exit__`. Callers above this boundary hold no connection, no cursor,
    and no `psycopg` import: `with reader:` is plain Python, not a driver
    detail.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresBronzeReader:
        """Open the connection and cursor this block's statements share."""
        self._conn = psycopg.connect(self._database_url)
        self._cur = self._conn.cursor()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Commit on a clean exit, roll back if the block raised, and close
        both the cursor and the connection either way.

        Returns None so a failure inside the block still propagates: a
        repository must not swallow its caller's exception.
        """
        try:
            if self._cur is not None:
                self._cur.close()
            if self._conn is not None:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
        finally:
            if self._conn is not None:
                self._conn.close()
            self._cur = None
            self._conn = None
        return None

    def read(self, source: str) -> list[dict]:
        """Return every current payload for `source`."""
        self._cur.execute(_SELECT_SQL, (source,))
        return [row[0] for row in self._cur.fetchall()]
