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
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def read_hn_postings(self) -> list[StagedSignal]:
        return self._read("hn", _HN_STAGING_SELECT_SQL)

    def read_yc_listings(self) -> list[StagedSignal]:
        return self._read("yc", _YC_STAGING_SELECT_SQL)

    def _read(self, source: str, select_sql: str) -> list[StagedSignal]:
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(select_sql)
            return [_row_to_staged_signal(source, row) for row in cur.fetchall()]


class PostgresResolvedSignalWriter:
    """`ResolvedSignalWriterPort` implementation against
    silver.resolved_signals. Knows only how to upsert one row.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def upsert(self, record: ResolvedSignalRecord) -> None:
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.execute(
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
