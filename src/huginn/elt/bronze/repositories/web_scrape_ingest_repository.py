"""Postgres persistence for `bronze.web_scrape_ingest`."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

_LOOKUP_SQL = """
    SELECT content_hash
    FROM bronze.web_scrape_ingest
    WHERE source = %s AND stable_id = %s
"""

_WRITE_SQL = """
    INSERT INTO bronze.web_scrape_ingest
        (source, stable_id, payload, content_hash, run_id)
    VALUES (%s, %s, %s, %s, %s::uuid)
    ON CONFLICT (source, stable_id) DO UPDATE
    SET payload = EXCLUDED.payload,
        content_hash = EXCLUDED.content_hash,
        run_id = EXCLUDED.run_id,
        fetched_at = now(),
        last_checked_at = now()
    WHERE EXCLUDED.source <> 'eu_startups'
       OR (
            EXCLUDED.payload ->> 'lastmod' IS NOT NULL
            AND (
                bronze.web_scrape_ingest.payload ->> 'lastmod' IS NULL
                OR (bronze.web_scrape_ingest.payload ->> 'lastmod')::timestamptz
                   <= (EXCLUDED.payload ->> 'lastmod')::timestamptz
            )
       )
"""

_TOUCH_SQL = """
    UPDATE bronze.web_scrape_ingest
    SET last_checked_at = now()
    WHERE source = %s AND stable_id = %s
"""


def build_lookup_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]:
    return _LOOKUP_SQL, (source, stable_id)


def build_write_query(
    source: str, stable_id: str, payload: dict, content_hash: str, run_id: str
) -> tuple[str, tuple[str, str, Jsonb, str, str]]:
    return _WRITE_SQL, (source, stable_id, Jsonb(payload), content_hash, run_id)


def build_touch_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]:
    return _TOUCH_SQL, (source, stable_id)


class PostgresWebScrapeIngestRepository:
    """One-transaction repository for `bronze.web_scrape_ingest`."""

    bronze_table = "web_scrape_ingest"

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None
        self._cur = None

    def __enter__(self) -> PostgresWebScrapeIngestRepository:
        self._conn = psycopg.connect(self._database_url)
        self._cur = self._conn.cursor()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
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
        self._cur.execute(
            *build_write_query(source, stable_id, payload, content_hash, run_id)
        )

    def touch(self, source: str, stable_id: str) -> None:
        self._cur.execute(*build_touch_query(source, stable_id))
