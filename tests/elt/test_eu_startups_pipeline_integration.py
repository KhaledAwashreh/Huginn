from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from huginn.config import Config
from huginn.elt import materialization
from huginn.elt.materialization import build_eu_startups_materialization_stages
from huginn.elt.silver import signal_resolution
from huginn.elt.stage_runner import Stage, run_stages
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
    other_domain = f"eu-other-{suffix}.example"
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

    stages = build_eu_startups_materialization_stages(
        Config(database_url=database_url, yc_algolia_api_key="test"),
        include_manual_review=False,
        resolve_eu_startups_only=True,
    )
    stage_counts = {stage.name: stage.run() for stage in stages}
    assert stage_counts == {
        "silver.eu_startups_staging": 1,
        "silver.signal_resolution": 1,
        "gold.company": 1,
        "gold.company_signal": 1,
        "silver.source_currentness.eu_startups": 1,
    }

    with psycopg.connect(database_url) as conn:
        other_company_id = conn.execute(
            "INSERT INTO gold.company (domain, name) VALUES (%s, 'Other') RETURNING id",
            (other_domain,),
        ).fetchone()[0]

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT company_name_raw, website, founded, total_funding, "
            "company_status FROM silver.eu_startups_listings "
            "WHERE stable_id = %s",
            (stable_id,),
        )
        assert cur.fetchone() == (
            company_name,
            f"https://{domain}",
            "2024",
            "No funding announced yet",
            "Active",
        )

        cur.execute(
            "SELECT resolved_company_key, key_derivation, company_status, "
            "founded, total_funding "
            "FROM silver.resolved_signals "
            "WHERE source = 'eu_startups' AND source_stable_id = %s",
            (stable_id,),
        )
        assert cur.fetchone() == (
            domain,
            "domain_normalized",
            "Active",
            "2024",
            "No funding announced yet",
        )

        cur.execute(
            "SELECT c.name, c.company_status, c.notes, cs.source_url "
            "FROM gold.company c "
            "JOIN gold.company_signal cs ON cs.company_id = c.id "
            "WHERE c.domain = %s AND cs.source = 'eu_startups' "
            "AND cs.source_stable_id = %s",
            (domain, stable_id),
        )
        assert cur.fetchone() == (
            company_name,
            "Active",
            "EU Startups Founded 2024; EU Startups Funding No funding announced yet",
            listing_url,
        )

        cur.execute(
            "SELECT observation.id, pointer.current_observation_id, "
            "observation.listing_state, observation.identity_state, "
            "observation.company_id FROM silver.source_lifecycle_observation "
            "observation JOIN silver.source_currentness pointer USING (source, stable_id) "
            "WHERE source = 'eu_startups' AND stable_id = %s",
            (stable_id,),
        )
        observation_id, current_id, listing_state, identity_state, company_id = (
            cur.fetchone()
        )
        assert observation_id == current_id
        assert (listing_state, identity_state) == ("available", "consistent")

        cur.execute(
            "SELECT source, evidence_kind, source_url, company_id "
            "FROM gold.current_source_evidence WHERE source_stable_id = %s",
            (stable_id,),
        )
        assert cur.fetchone() == (
            "eu_startups",
            "directory_context",
            listing_url,
            company_id,
        )

        cur.execute(
            "UPDATE bronze.web_scrape_ingest SET payload = '{}'::jsonb "
            "WHERE source = 'eu_startups' AND stable_id = %s",
            (stable_id,),
        )
        conn.commit()
        cur.execute(
            "SELECT count(*) FROM gold.current_source_evidence "
            "WHERE source_stable_id = %s",
            (stable_id,),
        )
        assert cur.fetchone() == (0,)

    reports = []
    original_run_reconcile = materialization.run_reconcile

    def capture_partial_report(source, repository):
        report = original_run_reconcile(source, repository)
        reports.append(report)
        return report

    monkeypatch.setattr(materialization, "run_reconcile", capture_partial_report)
    currentness_stage = stages[-1]
    with pytest.raises(RuntimeError, match="reconciliation incomplete"):
        currentness_stage.run()
    assert reports[-1]["status"] == "partial"
    assert reports[-1]["completed_count"] == 1
    with psycopg.connect(database_url) as conn:
        partial_observation_id, partial_state = conn.execute(
            "SELECT observation.id, observation.listing_state "
            "FROM silver.source_lifecycle_observation observation "
            "JOIN silver.source_currentness pointer USING (source, stable_id) "
            "WHERE source = 'eu_startups' AND stable_id = %s "
            "AND pointer.current_observation_id = observation.id",
            (stable_id,),
        ).fetchone()
        assert partial_observation_id != observation_id
        assert partial_state == "invalid"
        assert conn.execute(
            "SELECT count(*) FROM gold.current_source_evidence "
            "WHERE source_stable_id = %s",
            (stable_id,),
        ).fetchone() == (0,)

    with psycopg.connect(database_url) as conn:
        conn.execute(
            "UPDATE bronze.web_scrape_ingest SET payload = %s "
            "WHERE source = 'eu_startups' AND stable_id = %s",
            (psycopg.types.json.Jsonb(payload), stable_id),
        )
    monkeypatch.setattr(materialization, "run_reconcile", original_run_reconcile)
    assert currentness_stage.run() == 1
    with psycopg.connect(database_url) as conn:
        restored_observation_id = conn.execute(
            "SELECT current_observation_id FROM silver.source_currentness "
            "WHERE source = 'eu_startups' AND stable_id = %s",
            (stable_id,),
        ).fetchone()[0]
        assert restored_observation_id != partial_observation_id
        assert conn.execute(
            "SELECT count(*) FROM gold.current_source_evidence "
            "WHERE source_stable_id = %s",
            (stable_id,),
        ).fetchone() == (1,)
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "UPDATE gold.company_signal SET company_id = %s "
            "WHERE source = 'eu_startups' AND source_stable_id = %s",
            (other_company_id, stable_id),
        )
        assert conn.execute(
            "SELECT count(*) FROM gold.current_source_evidence "
            "WHERE source_stable_id = %s",
            (stable_id,),
        ).fetchone() == (0,)
        conn.execute(
            "UPDATE gold.company_signal SET company_id = %s "
            "WHERE source = 'eu_startups' AND source_stable_id = %s",
            (company_id, stable_id),
        )
        assert conn.execute(
            "SELECT count(*) FROM gold.current_source_evidence "
            "WHERE source_stable_id = %s",
            (stable_id,),
        ).fetchone() == (1,)

        class RecordingWriter:
            def write(self, _job_run):
                pass

        def fail_hn_reconciliation():
            raise RuntimeError("HN reconciliation partial")

        statuses = run_stages(
            [
                Stage("gold.company_signal", lambda: 0),
                Stage(
                    "silver.source_currentness.hn",
                    fail_hn_reconciliation,
                    depends_on=("gold.company_signal",),
                ),
                currentness_stage,
            ],
            RecordingWriter(),
        )
        assert statuses == {
            "gold.company_signal": "succeeded",
            "silver.source_currentness.hn": "failed",
            "silver.source_currentness.eu_startups": "succeeded",
        }
        assert conn.execute(
            "SELECT count(*) FROM gold.current_source_evidence "
            "WHERE source_stable_id = %s",
            (stable_id,),
        ).fetchone() == (1,)
