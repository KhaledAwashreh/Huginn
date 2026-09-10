"""Postgres repository for `bronze.api_ingest`: the only module holding
that table's SQL and the only one that opens a connection to run it.

Both `PostgresApiIngestStore` (a `RawStorePort`) and
`PostgresApiIngestState` (a `StatePort`) sit on top of this class, so the
"stored content_hash for (source, stable_id)" lookup exists once here
rather than once per consumer. See architecture document section 4.1
point 4 (skip-on-hash-match write), BEST_PRACTICES.md section 8.1 (bind
parameters only, never string-built SQL), and ADR-0005 (logging required
from day one).
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

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
    existing one with a changed hash overwrites in place. Bronze's
    `UNIQUE (source, stable_id)` allows exactly one row per entity, so the
    changed-hash case is an in-place overwrite, not a new version.
    """
    return _WRITE_SQL, (source, stable_id, Jsonb(payload), content_hash, run_id)


def build_touch_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]:
    """Parameterized UPDATE bumping last_checked_at only, no payload or
    content_hash change, for a hash-match skip. Architecture document
    section 4.1 point 4.
    """
    return _TOUCH_SQL, (source, stable_id)


class PostgresApiIngestRepository:
    """`ApiIngestRepositoryPort` implementation against `bronze.api_ingest`.

    A context manager: one connection and one cursor span the whole `with`
    block, so an orchestrator's entire batch shares a single connection and
    a single transaction. A connection per row would mean thousands of
    connects on a large run, and would commit each record independently
    rather than atomically per orchestrator call.

    `lookup_hash`, `write`, and `touch` therefore assume they are called
    between `__enter__` and `__exit__`. Callers above this boundary hold no
    connection, no cursor, and no `psycopg` import: `with repository:` is
    plain Python, not a driver detail.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresApiIngestRepository:
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

    def lookup_hash(self, source: str, stable_id: str) -> str | None:
        """See huginn.elt.bronze.ports.ApiIngestRepositoryPort.lookup_hash."""
        self._cur.execute(*build_lookup_query(source, stable_id))
        row = self._cur.fetchone()
        return row[0] if row else None

    def write(
        self,
        source: str,
        stable_id: str,
        payload: dict,
        content_hash: str,
        run_id: str,
    ) -> None:
        """See huginn.elt.bronze.ports.ApiIngestRepositoryPort.write."""
        self._cur.execute(
            *build_write_query(source, stable_id, payload, content_hash, run_id)
        )

    def touch(self, source: str, stable_id: str) -> None:
        """See huginn.elt.bronze.ports.ApiIngestRepositoryPort.touch."""
        self._cur.execute(*build_touch_query(source, stable_id))
