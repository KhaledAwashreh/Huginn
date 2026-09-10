"""Postgres-backed `YcStagingRepositoryPort`. See huginn.silver.ports,
huginn.silver.yc_staging (the parser and orchestrator this persists for),
and docs/entities.md's YcListingStaging. Jira KAN-34.
"""

from __future__ import annotations

from typing import Self

from huginn.silver.postgres_repository import (
    PostgresConnectionScope,
    read_bronze_payloads,
)
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
    (db/schema/silver.sql's UNIQUE(stable_id) on silver.yc_listings)."""
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
    """`YcStagingRepositoryPort` implementation: reads bronze.api_ingest
    and upserts silver.yc_listings. No orchestration, no parsing.

    Composes a `PostgresConnectionScope` for its connection lifecycle
    rather than inheriting one, consistent with this codebase's
    dependency-injection style elsewhere. Both `read` and `upsert` live on
    one class so `YcStagingLoader.load()` needs a single connection and a
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

    def upsert(self, row: YcListingStaging) -> None:
        self._scope.cursor.execute(*build_upsert_query(row))
