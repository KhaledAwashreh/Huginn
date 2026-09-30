from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from huginn.elt.silver.eu_startups_staging import (
    EuStartupsStagingLoader,
    parse_eu_startups_listing,
)
from huginn.elt.silver.models import EuStartupsListingStaging
from huginn.elt.silver.repositories.eu_startups_staging_repository import (
    PostgresEuStartupsStagingRepository,
)

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"


def test_load_round_trips_eu_startups_bronze_payload_into_silver(
    integration_database_url: str,
):
    stable_id = f"integration-{uuid.uuid4().hex}"
    run_id = str(uuid.uuid4())
    payload = {
        "url": f"https://www.eu-startups.com/directory/{stable_id}/",
        "html": (_FIXTURES / "listing_brightroom.html")
        .read_text(encoding="utf-8")
        .replace("Brightroom", "Integration Brightroom"),
        "lastmod": "2026-09-01T07:37:16+00:00",
    }

    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.web_scrape_ingest
                (source, stable_id, payload, content_hash, run_id)
            VALUES ('eu_startups', %s, %s, 'test-hash', %s::uuid)
            """,
            (stable_id, psycopg.types.json.Jsonb(payload), run_id),
        )

    try:
        loader = EuStartupsStagingLoader(
            PostgresEuStartupsStagingRepository(integration_database_url)
        )
        assert loader.load() >= 1

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT company_name_raw, website, signal_type, stage, description,
                       occurred_on, url
                FROM silver.eu_startups_listings
                WHERE stable_id = %s
                """,
                (stable_id,),
            )
            assert cur.fetchone() == (
                "Integration Brightroom",
                "https://thebrightroom.de",
                "other",
                None,
                parse_eu_startups_listing(payload).description,
                datetime(2026, 9, 1, 7, 37, 16, tzinfo=UTC),
                payload["url"],
            )

        changed = EuStartupsListingStaging(
            stable_id=stable_id,
            company_name_raw="Updated Integration Brightroom",
            website="https://updated.example",
            signal_type="other",
            stage=None,
            description="Updated description.",
            occurred_on=datetime(2026, 9, 2, 8, 0, tzinfo=UTC),
            url=payload["url"],
        )
        with PostgresEuStartupsStagingRepository(integration_database_url) as repo:
            repo.upsert(changed)

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*), company_name_raw, website, description, occurred_on
                FROM silver.eu_startups_listings
                WHERE stable_id = %s
                GROUP BY company_name_raw, website, description, occurred_on
                """,
                (stable_id,),
            )
            assert cur.fetchone() == (
                1,
                "Updated Integration Brightroom",
                "https://updated.example",
                "Updated description.",
                datetime(2026, 9, 2, 8, 0, tzinfo=UTC),
            )
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.eu_startups_listings WHERE stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                """
                DELETE FROM bronze.web_scrape_ingest
                WHERE source = 'eu_startups' AND stable_id = %s
                """,
                (stable_id,),
            )
