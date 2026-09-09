"""Shared Postgres adapter infrastructure for the Silver repositories: the
connection scope every one of them needs, and the bronze.api_ingest read
the two staging repositories share. See huginn.silver.ports for the port
contracts these support and architecture document section 4.1 for the one
shared api_ingest table.
"""

from __future__ import annotations

from typing import Self

import psycopg

_BRONZE_SELECT_SQL = "SELECT payload FROM bronze.api_ingest WHERE source = %s"


class PostgresRepositoryScope:
    """One connection and one cursor spanning a whole `with` block.

    Base class for every Silver repository, so the commit/rollback rule
    lives in one place rather than in a copy per adapter. See
    huginn.silver.ports' connection-scope note: the scope belongs to the
    orchestrator's whole call, so its entire batch shares a single
    connection and a single transaction. Subclasses' data methods use
    `self._cur` and are only valid between `__enter__` and `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> Self:
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


class PostgresBronzeReadingRepository(PostgresRepositoryScope):
    """Adds the bronze.api_ingest read to the connection scope.

    Base for both staging repositories rather than a class of its own: the
    read side is identical regardless of source (architecture document
    section 4.1, one shared api_ingest table with a `source` column), so
    the query has one owner even though HN and YC write to different
    tables.
    """

    def read(self, source: str) -> list[dict]:
        """Return every current bronze payload for `source`."""
        self._cur.execute(_BRONZE_SELECT_SQL, (source,))
        return [row[0] for row in self._cur.fetchall()]
