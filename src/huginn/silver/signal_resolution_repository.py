"""Postgres-backed `SignalResolutionRepositoryPort`. See
huginn.silver.ports, huginn.silver.signal_resolution (the resolver and
orchestrator this persists for), and docs/entities.md's ResolvedSignal.
Jira KAN-35.
"""

from __future__ import annotations

from huginn.silver.ports import ResolvedSignalRecord, StagedSignal
from huginn.silver.postgres_repository import PostgresRepositoryScope

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


class PostgresSignalResolutionRepository(PostgresRepositoryScope):
    """`SignalResolutionRepositoryPort` implementation: reads the
    per-source staging tables and upserts silver.resolved_signals. Knows
    no resolution logic.

    Both sides live on one class so `SignalResolver.resolve_all()` needs a
    single connection and a single transaction for its whole call, rather
    than one per port. That also puts the staging reads and the
    resolved_signals writes in one transaction, so the batch is resolved
    against a single consistent snapshot. Every method here is only valid
    between `__enter__` and `__exit__`.
    """

    def read_hn_postings(self) -> list[StagedSignal]:
        return self._read("hn", _HN_STAGING_SELECT_SQL)

    def read_yc_listings(self) -> list[StagedSignal]:
        return self._read("yc", _YC_STAGING_SELECT_SQL)

    def _read(self, source: str, select_sql: str) -> list[StagedSignal]:
        self._cur.execute(select_sql)
        return [_row_to_staged_signal(source, row) for row in self._cur.fetchall()]

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
