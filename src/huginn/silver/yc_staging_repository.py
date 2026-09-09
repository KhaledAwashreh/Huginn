"""Postgres-backed `YcStagingWriterPort`. See huginn.silver.ports,
huginn.silver.yc_staging (the parser and orchestrator this persists
for), and docs/entities.md's YcListingStaging. Jira KAN-34.
"""

from __future__ import annotations

import psycopg

from huginn.silver.yc_staging import YcListingStaging

_UPSERT_SQL = """
    INSERT INTO silver.yc_listings
        (stable_id, company_name_raw, website, signal_type, stage,
         description, occurred_on, url)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (stable_id) DO UPDATE
    SET company_name_raw = EXCLUDED.company_name_raw,
        website = EXCLUDED.website,
        signal_type = EXCLUDED.signal_type,
        stage = EXCLUDED.stage,
        description = EXCLUDED.description,
        occurred_on = EXCLUDED.occurred_on,
        url = EXCLUDED.url,
        updated_at = now()
"""


def build_upsert_query(row: YcListingStaging) -> tuple[str, tuple]:
    """Parameterized upsert for one staging row, keyed on stable_id
    (see huginn.silver.ports.py's Task 1 unique constraint)."""
    return _UPSERT_SQL, (
        row.stable_id,
        row.company_name_raw,
        row.website,
        row.signal_type,
        row.stage,
        row.description,
        row.occurred_on,
        row.url,
    )


class PostgresYcStagingRepository:
    """`YcStagingWriterPort` implementation against silver.yc_listings.
    Knows only how to upsert one row; no orchestration, no bronze read.

    A context manager: one connection and one cursor span the whole `with`
    block, so a loader's entire batch shares a single connection and a
    single transaction (see huginn.silver.ports' connection-scope note).
    `upsert` therefore assumes it is called between `__enter__` and
    `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresYcStagingRepository:
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

    def upsert(self, row: YcListingStaging) -> None:
        self._cur.execute(*build_upsert_query(row))
