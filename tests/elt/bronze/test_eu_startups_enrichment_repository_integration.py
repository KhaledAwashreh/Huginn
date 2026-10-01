from __future__ import annotations

import uuid

import psycopg
from psycopg.types.json import Jsonb

from huginn.elt.bronze.repositories.eu_startups_enrichment_repository import (
    PostgresEuStartupsEnrichmentRepository,
)
from huginn.elt.ingestion.models import (
    EnrichmentBatch,
    EnrichmentCandidateOutcome,
    EnrichmentOutcomeStatus,
    RawRecord,
)


def test_newer_discovery_row_is_preserved_and_all_same_name_rows_are_marked(
    integration_database_url: str,
):
    """Exercise real PostgreSQL JSONB, upsert guards, and Gold cursor SQL.

    The shared integration fixture provisions a throwaway database; unique
    company IDs and a unique listing slug keep this case isolated from other
    tests and user data.
    """
    candidate_name = f"KAN83 enrichment {uuid.uuid4()}"
    stable_id = f"kan83-enrichment-{uuid.uuid4().hex}"
    run_id = str(uuid.uuid4())
    company_ids = []
    discovery_payload = {
        "url": f"https://www.eu-startups.com/directory/{stable_id}/",
        "html": "<main>newer discovery payload</main>",
        "lastmod": "2026-10-01T10:00:00+00:00",
    }
    enrichment_payload = {
        "url": discovery_payload["url"],
        "html": "<main>older enrichment payload</main>",
        "lastmod": "2026-09-30T10:00:00+00:00",
    }

    try:
        with (
            psycopg.connect(integration_database_url) as connection,
            connection.cursor() as cursor,
        ):
            for _ in range(2):
                cursor.execute(
                    "INSERT INTO gold.company (domain, name) "
                    "VALUES (%s, %s) RETURNING id",
                    (f"{uuid.uuid4().hex}.integration.invalid", candidate_name),
                )
                company_ids.append(cursor.fetchone()[0])
            cursor.execute(
                "INSERT INTO bronze.web_scrape_ingest "
                "(source, stable_id, payload, content_hash, run_id) "
                "VALUES ('eu_startups', %s, %s, %s, %s::uuid)",
                (
                    stable_id,
                    Jsonb(discovery_payload),
                    "discovery-content-hash",
                    str(uuid.uuid4()),
                ),
            )
            cursor.execute(
                "SELECT last_checked_at FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            )
            first_checked_at = cursor.fetchone()[0]

        batch = EnrichmentBatch(
            records=(RawRecord(stable_id, enrichment_payload),),
            outcomes=(
                EnrichmentCandidateOutcome(
                    candidate_name, EnrichmentOutcomeStatus.ENRICHED
                ),
            ),
        )
        written = PostgresEuStartupsEnrichmentRepository(
            integration_database_url
        ).persist_batch(batch, run_id)

        with psycopg.connect(integration_database_url) as connection:
            bronze_row = connection.execute(
                "SELECT payload, content_hash, last_checked_at "
                "FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            ).fetchone()
            searched_count = connection.execute(
                "SELECT count(*) FROM gold.company "
                "WHERE name = %s AND eu_startups_searched_at IS NOT NULL",
                (candidate_name,),
            ).fetchone()[0]

        assert written == 0
        assert bronze_row[0] == discovery_payload
        assert bronze_row[1] == "discovery-content-hash"
        assert bronze_row[2] > first_checked_at
        assert searched_count == 2
    finally:
        with psycopg.connect(integration_database_url) as connection:
            if company_ids:
                connection.execute(
                    "DELETE FROM gold.company WHERE id = ANY(%s)", (company_ids,)
                )
            connection.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            )
