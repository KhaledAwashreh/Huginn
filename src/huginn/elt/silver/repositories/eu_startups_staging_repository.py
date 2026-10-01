"""Postgres-backed `EuStartupsStagingRepositoryPort` implementation."""

from __future__ import annotations

from typing import Self

from huginn.elt.silver.models import EuStartupsListingStaging
from huginn.elt.silver.repositories.postgres_repository import (
    PostgresConnectionScope,
    read_web_scrape_payloads,
)

_UPSERT_SQL = """
    INSERT INTO silver.eu_startups_listings
        (stable_id, company_name_raw, website, signal_type, stage,
         description, occurred_on, url, founded, total_funding, company_status)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (stable_id) DO UPDATE
    SET company_name_raw = EXCLUDED.company_name_raw,
        website = EXCLUDED.website,
        signal_type = EXCLUDED.signal_type,
        stage = EXCLUDED.stage,
        description = EXCLUDED.description,
        occurred_on = EXCLUDED.occurred_on,
        url = EXCLUDED.url,
        founded = EXCLUDED.founded,
        total_funding = EXCLUDED.total_funding,
        company_status = EXCLUDED.company_status,
        updated_at = now()
"""


def build_upsert_query(row: EuStartupsListingStaging) -> tuple[str, tuple]:
    """Build the parameterized upsert keyed by the listing's stable ID."""
    return _UPSERT_SQL, (
        row.stable_id,
        row.company_name_raw,
        row.website,
        row.signal_type,
        row.stage,
        row.description,
        row.occurred_on,
        row.url,
        row.founded,
        row.total_funding,
        row.company_status,
    )


class PostgresEuStartupsStagingRepository:
    """Reads bronze.web_scrape_ingest and upserts silver.eu_startups_listings.

    The shared connection scope keeps each loader batch in one transaction,
    matching the HN and YC staging adapters.
    """

    def __init__(self, database_url: str) -> None:
        self._scope = PostgresConnectionScope(database_url)

    def __enter__(self) -> Self:
        self._scope.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return self._scope.__exit__(exc_type, exc_value, traceback)

    def read(self, source: str) -> list[dict]:
        return read_web_scrape_payloads(self._scope.cursor, source)

    def upsert(self, row: EuStartupsListingStaging) -> None:
        self._scope.cursor.execute(*build_upsert_query(row))
