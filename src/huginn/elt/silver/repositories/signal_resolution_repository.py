"""Postgres-backed `SignalResolutionRepositoryPort`. See
huginn.elt.silver.ports, huginn.elt.silver.signal_resolution (the resolver and
orchestrator this persists for), and docs/entities.md's ResolvedSignal.
Jira KAN-35.
"""

from __future__ import annotations

from typing import Self

from huginn.elt.silver.models import ResolvedSignalRecord, StagedSignal
from huginn.elt.silver.repositories.postgres_repository import PostgresConnectionScope

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
         signal_type, stage, description, occurred_on, url, key_derivation)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (source, source_stable_id) DO UPDATE
    SET resolved_company_key = EXCLUDED.resolved_company_key,
        company_name_raw = EXCLUDED.company_name_raw,
        signal_type = EXCLUDED.signal_type,
        stage = EXCLUDED.stage,
        description = EXCLUDED.description,
        occurred_on = EXCLUDED.occurred_on,
        url = EXCLUDED.url,
        key_derivation = EXCLUDED.key_derivation,
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


class PostgresSignalResolutionRepository:
    """`SignalResolutionRepositoryPort` implementation: reads the
    per-source staging tables and upserts silver.resolved_signals. Knows
    no resolution logic.

    Composes a `PostgresConnectionScope` for its connection lifecycle
    rather than inheriting one, consistent with this codebase's
    dependency-injection style elsewhere. Both sides live on one class so
    `SignalResolver.resolve_all()` needs a single connection and a single
    transaction for its whole call, rather than one per port. That also
    puts the staging reads and the resolved_signals writes in one
    transaction, so the batch is resolved against a single consistent
    snapshot. Every method here is only valid between `__enter__` and
    `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._scope = PostgresConnectionScope(database_url)

    def __enter__(self) -> Self:
        self._scope.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return self._scope.__exit__(exc_type, exc_value, traceback)

    def read_hn_postings(self) -> list[StagedSignal]:
        return self._read("hn", _HN_STAGING_SELECT_SQL)

    def read_yc_listings(self) -> list[StagedSignal]:
        return self._read("yc", _YC_STAGING_SELECT_SQL)

    def _read(self, source: str, select_sql: str) -> list[StagedSignal]:
        self._scope.cursor.execute(select_sql)
        return [
            _row_to_staged_signal(source, row) for row in self._scope.cursor.fetchall()
        ]

    def upsert(self, record: ResolvedSignalRecord) -> None:
        self._scope.cursor.execute(
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
                record.key_derivation,
            ),
        )
