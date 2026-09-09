"""Postgres-backed `YcStagingRepositoryPort`. See huginn.silver.ports,
huginn.silver.yc_staging (the parser and orchestrator this persists for),
and docs/entities.md's YcListingStaging. Jira KAN-34.
"""

from __future__ import annotations

from huginn.silver.postgres_repository import PostgresBronzeReadingRepository
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


class PostgresYcStagingRepository(PostgresBronzeReadingRepository):
    """`YcStagingRepositoryPort` implementation: reads bronze.api_ingest
    and upserts silver.yc_listings. No orchestration, no parsing.

    Both sides live on one class so `YcStagingLoader.load()` needs a single
    connection and a single transaction for its whole batch, rather than
    one per port. `read` comes from `PostgresBronzeReadingRepository`; both
    it and `upsert` are only valid between `__enter__` and `__exit__`.
    """

    def upsert(self, row: YcListingStaging) -> None:
        self._cur.execute(*build_upsert_query(row))
