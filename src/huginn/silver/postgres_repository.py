"""Shared Postgres adapter infrastructure for the Silver repositories: the
connection scope every one of them needs, and the bronze.api_ingest read
the two staging repositories share. Composed by each concrete repository,
not inherited — consistent with this codebase's dependency-injection
style everywhere else (ports passed into constructors, never a shared
base class). See huginn.silver.ports for the port contracts these
support and architecture document section 4.1 for the one shared
api_ingest table.
"""

from __future__ import annotations

from typing import Self

import psycopg

_BRONZE_SELECT_SQL = "SELECT payload FROM bronze.api_ingest WHERE source = %s"


class PostgresConnectionScope:
    """One connection and one cursor spanning a whole `with` block.

    Composed by every Silver repository so the commit/rollback rule lives
    in one place rather than in a copy per adapter, without making the
    repositories inherit from a shared base. The scope belongs to the
    orchestrator's whole call: a repository's `__enter__`/`__exit__`
    delegate to this object's, and its data methods use `self.cursor`,
    valid only between `__enter__` and `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self.cursor = None

    def __enter__(self) -> Self:
        """Open the connection and cursor this block's statements share."""
        self._conn = psycopg.connect(self._database_url)
        self.cursor = self._conn.cursor()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Commit on a clean exit, roll back if the block raised, and close
        both the cursor and the connection either way.

        Returns None so a failure inside the block still propagates: a
        repository must not swallow its caller's exception.
        """
        try:
            if self.cursor is not None:
                self.cursor.close()
            if self._conn is not None:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
        finally:
            if self._conn is not None:
                self._conn.close()
            self.cursor = None
            self._conn = None
        return None


def read_bronze_payloads(cursor, source: str) -> list[dict]:
    """Return every current bronze payload for `source`, using an
    already-open cursor. Shared by both staging repositories as a plain
    function, not a base class: the read side is identical regardless of
    source (architecture document section 4.1, one shared api_ingest
    table with a `source` column), so the query has one owner even though
    HN and YC write to different tables.
    """
    cursor.execute(_BRONZE_SELECT_SQL, (source,))
    return [row[0] for row in cursor.fetchall()]
