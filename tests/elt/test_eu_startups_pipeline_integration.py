from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from huginn.elt.gold.company import CompanyWriter
from huginn.elt.gold.company_signal import CompanySignalWriter
from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository
from huginn.elt.gold.repositories.company_signal_repository import (
    PostgresCompanySignalRepository,
)
from huginn.elt.silver import signal_resolution
from huginn.elt.silver.eu_startups_staging import EuStartupsStagingLoader
from huginn.elt.silver.repositories.eu_startups_staging_repository import (
    PostgresEuStartupsStagingRepository,
)
from huginn.elt.silver.repositories.signal_resolution_repository import (
    PostgresSignalResolutionRepository,
)
from huginn.elt.silver.signal_resolution import SignalResolver
from tests.postgres_harness import provisioned_postgres

_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "eu_startups"
    / "listing_brightroom.html"
)


@pytest.fixture
def eu_pipeline_database_url() -> Iterator[str]:
    """Use a dedicated database because every writer below scans its table."""
    with provisioned_postgres("huginn_eu_pipeline") as database_url:
        yield database_url


def test_eu_startups_listing_flows_from_bronze_through_gold(
    eu_pipeline_database_url: str, monkeypatch
):
    database_url = eu_pipeline_database_url
    suffix = uuid.uuid4().hex
    stable_id = f"pipeline-{suffix}"
    company_name = f"EU Pipeline {suffix}"
    domain = f"eu-pipeline-{suffix}.example"
    listing_url = f"https://www.eu-startups.com/directory/{stable_id}/"
    html = (
        _FIXTURE.read_text(encoding="utf-8")
        .replace("Brightroom", company_name)
        .replace("https://thebrightroom.de", f"https://{domain}")
    )
    payload = {
        "url": listing_url,
        "html": html,
        "lastmod": "2026-09-01T07:37:16+00:00",
    }

    monkeypatch.setattr(
        signal_resolution,
        "check_domain_reachable",
        lambda checked_domain, timeout=5.0: checked_domain == domain,
    )

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.web_scrape_ingest
                (source, stable_id, payload, content_hash, run_id)
            VALUES ('eu_startups', %s, %s, %s, %s::uuid)
            """,
            (
                stable_id,
                psycopg.types.json.Jsonb(payload),
                f"pipeline-{suffix}",
                str(uuid.uuid4()),
            ),
        )

    try:
        staged = EuStartupsStagingLoader(
            PostgresEuStartupsStagingRepository(database_url)
        ).load()
        resolved = SignalResolver(
            PostgresSignalResolutionRepository(database_url)
        ).resolve_all()
        companies = CompanyWriter(PostgresCompanyRepository(database_url)).write_all()
        facts = CompanySignalWriter(
            PostgresCompanySignalRepository(database_url)
        ).write_all()

        assert staged >= 1
        assert resolved >= 1
        assert companies >= 1
        assert facts >= 1

        with psycopg.connect(database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT company_name_raw, website FROM silver.eu_startups_listings "
                "WHERE stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone() == (company_name, f"https://{domain}")

            cur.execute(
                "SELECT resolved_company_key, key_derivation "
                "FROM silver.resolved_signals "
                "WHERE source = 'eu_startups' AND source_stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone() == (domain, "domain_normalized")

            cur.execute(
                "SELECT c.name, cs.source_url "
                "FROM gold.company c "
                "JOIN gold.company_signal cs ON cs.company_id = c.id "
                "WHERE c.domain = %s AND cs.source = 'eu_startups' "
                "AND cs.source_stable_id = %s",
                (domain, stable_id),
            )
            assert cur.fetchone() == (company_name, listing_url)
    finally:
        with psycopg.connect(database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company_signal "
                "WHERE source = 'eu_startups' AND source_stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.manual_review_queue WHERE resolved_signal_id IN "
                "(SELECT id FROM silver.resolved_signals "
                "WHERE source = 'eu_startups' AND source_stable_id = %s)",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.resolved_signals "
                "WHERE source = 'eu_startups' AND source_stable_id = %s",
                (stable_id,),
            )
            cur.execute("DELETE FROM gold.company_history WHERE domain = %s", (domain,))
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))
            cur.execute(
                "DELETE FROM silver.eu_startups_listings WHERE stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            )
