"""Postgres-backed `HnStagingRepositoryPort`. See huginn.elt.silver.ports,
huginn.elt.silver.hn_staging (the parser and orchestrator this persists for),
and docs/entities.md's HnPostingStaging. Jira KAN-34.
"""

from __future__ import annotations

from typing import Self

from huginn.elt.silver.models import HnPostingStaging
from huginn.elt.silver.repositories.postgres_repository import (
    PostgresConnectionScope,
    read_bronze_payloads,
)

_UPSERT_SQL = """
    INSERT INTO silver.hn_postings
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


def build_upsert_query(row: HnPostingStaging) -> tuple[str, tuple]:
    """Parameterized upsert for one staging row, keyed on stable_id
    (db/schema/silver.sql's UNIQUE(stable_id) on silver.hn_postings)."""
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


class PostgresHnStagingRepository:
    """`HnStagingRepositoryPort` implementation: reads bronze.api_ingest
    and upserts silver.hn_postings. No orchestration, no parsing.

    Composes a `PostgresConnectionScope` for its connection lifecycle
    rather than inheriting one, consistent with this codebase's
    dependency-injection style elsewhere. Both `read` and `upsert` live on
    one class so `HnStagingLoader.load()` needs a single connection and a
    single transaction for its whole batch, rather than one per port, and
    are only valid between `__enter__` and `__exit__`.
    """

    def __init__(self, database_url: str) -> None:
        self._scope = PostgresConnectionScope(database_url)

    def __enter__(self) -> Self:
        self._scope.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return self._scope.__exit__(exc_type, exc_value, traceback)

    def read(self, source: str) -> list[dict]:
        return read_bronze_payloads(self._scope.cursor, source)

    def upsert(self, row: HnPostingStaging) -> None:
        self._scope.cursor.execute(*build_upsert_query(row))
