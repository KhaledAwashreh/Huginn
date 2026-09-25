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

# Wider than the HN select by design: only silver.yc_listings has a registry
# status, a headcount, an industry list, a location, prior names, or a funded
# batch, so those six columns are projected here and not there. See ADR-0001
# on source-specific staging columns.
_YC_STAGING_SELECT_SQL = """
    SELECT stable_id, company_name_raw, website, signal_type, stage,
           description, occurred_on, url, company_status, team_size,
           industries, all_locations, former_names, batch
    FROM silver.yc_listings
"""

_UPSERT_SQL = """
    INSERT INTO silver.resolved_signals
        (source_stable_id, source, resolved_company_key, company_name_raw,
         signal_type, stage, description, occurred_on, url, key_derivation,
         company_status, team_size, industries, all_locations, former_names,
         batch)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (source, source_stable_id) DO UPDATE
    SET resolved_company_key = EXCLUDED.resolved_company_key,
        company_name_raw = EXCLUDED.company_name_raw,
        signal_type = EXCLUDED.signal_type,
        stage = EXCLUDED.stage,
        description = EXCLUDED.description,
        occurred_on = EXCLUDED.occurred_on,
        url = EXCLUDED.url,
        key_derivation = EXCLUDED.key_derivation,
        company_status = EXCLUDED.company_status,
        team_size = EXCLUDED.team_size,
        industries = EXCLUDED.industries,
        all_locations = EXCLUDED.all_locations,
        former_names = EXCLUDED.former_names,
        batch = EXCLUDED.batch,
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
    ) = row[:8]
    # A narrow row means the source's staging table has no such column at
    # all, which is the HN case: its comments carry no registry status, no
    # headcount, no industries, and no location. "Does not know", not a
    # value. Widening the guard in steps keeps each source's projection
    # independent of the others'.
    company_status, team_size = (row[8], row[9]) if len(row) > 9 else (None, None)
    industries, all_locations = (row[10], row[11]) if len(row) > 11 else (None, None)
    former_names = row[12] if len(row) > 12 else None
    batch = row[13] if len(row) > 13 else None
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
        company_status=company_status,
        team_size=team_size,
        industries=tuple(industries) if industries is not None else None,
        all_locations=all_locations,
        former_names=tuple(former_names) if former_names is not None else None,
        batch=batch,
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
        """Implement `SignalResolutionRepositoryPort.upsert`."""
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
                record.company_status,
                record.team_size,
                list(record.industries) if record.industries is not None else None,
                record.all_locations,
                list(record.former_names) if record.former_names is not None else None,
                record.batch,
            ),
        )
