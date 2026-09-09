"""Postgres-backed `SilverStagingReaderPort` and `ResolvedSignalWriterPort`.
See huginn.silver.ports, huginn.silver.signal_resolution (the resolver
and orchestrator these persist for), and docs/entities.md's
ResolvedSignal. Jira KAN-35.
"""

from __future__ import annotations

import psycopg

from huginn.silver.ports import ResolvedSignalRecord, StagedSignal

_HN_STAGING_SELECT_SQL = """
    SELECT stable_id, company_name_raw, website, signal_type, stage,
           description, occurred_on, url
    FROM silver.hn_postings
"""

_YC_STAGING_SELECT_SQL = """
    SELECT stable_id, company_name_raw, website, signal_type, stage,
           description, occurred_on, url
    FROM silver.yc_listings
"""

_UPSERT_SQL = """
    INSERT INTO silver.resolved_signals
        (source_stable_id, source, resolved_company_key, company_name_raw,
         signal_type, stage, description, occurred_on, url, match_confidence)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (source, source_stable_id) DO UPDATE
    SET resolved_company_key = EXCLUDED.resolved_company_key,
        company_name_raw = EXCLUDED.company_name_raw,
        signal_type = EXCLUDED.signal_type,
        stage = EXCLUDED.stage,
        description = EXCLUDED.description,
        occurred_on = EXCLUDED.occurred_on,
        url = EXCLUDED.url,
        match_confidence = EXCLUDED.match_confidence,
        updated_at = now()
"""


def _row_to_staged_signal(source: str, row: tuple) -> StagedSignal:
    (
        stable_id,
        company_name_raw,
        website,
        signal_type,
        stage,
        description,
        occurred_on,
        url,
    ) = row
    return StagedSignal(
        source=source,
        stable_id=stable_id,
        company_name_raw=company_name_raw,
        website=website,
        signal_type=signal_type,
        stage=stage,
        description=description,
        occurred_on=occurred_on,
        url=url,
    )


class PostgresSilverStagingReader:
    """`SilverStagingReaderPort` implementation against the per-source
    staging tables. Knows only how to read; no resolution logic.

    A context manager: one connection and one cursor span the whole `with`
    block, so the resolver's entire call shares a single connection and a
    single transaction (see huginn.silver.ports' connection-scope note).
    `read_hn_postings` and `read_yc_listings` therefore assume they are
    called between `__enter__` and `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresSilverStagingReader:
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

    def read_hn_postings(self) -> list[StagedSignal]:
        return self._read("hn", _HN_STAGING_SELECT_SQL)

    def read_yc_listings(self) -> list[StagedSignal]:
        return self._read("yc", _YC_STAGING_SELECT_SQL)

    def _read(self, source: str, select_sql: str) -> list[StagedSignal]:
        self._cur.execute(select_sql)
        return [_row_to_staged_signal(source, row) for row in self._cur.fetchall()]


class PostgresResolvedSignalWriter:
    """`ResolvedSignalWriterPort` implementation against
    silver.resolved_signals. Knows only how to upsert one row.

    A context manager: one connection and one cursor span the whole `with`
    block, so the resolver's entire batch shares a single connection and a
    single transaction (see huginn.silver.ports' connection-scope note).
    `upsert` therefore assumes it is called between `__enter__` and
    `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresResolvedSignalWriter:
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

    def upsert(self, record: ResolvedSignalRecord) -> None:
        self._cur.execute(
            _UPSERT_SQL,
            (
                record.source_stable_id,
                record.source,
                record.resolved_company_key,
                record.company_name_raw,
                record.signal_type,
                record.stage,
                record.description,
                record.occurred_on,
                record.url,
                record.match_confidence,
            ),
        )
