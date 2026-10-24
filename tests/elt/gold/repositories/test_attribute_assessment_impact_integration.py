"""Actual PostgreSQL impacts and invariants for fill and alias alternatives."""

from datetime import timedelta

import psycopg
import pytest

from huginn.elt.gold.repositories.attribute_assessment_repository import (
    PostgresAssessmentRepository,
)
from huginn.elt.gold.services.attribute_assessment import run_assessment
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow
from tests.matchmaking.test_evidence_integration import NOW, _reconcile, _seed_company
from tests.postgres_harness import provisioned_postgres


@pytest.fixture(scope="module")
def impact_database_url():
    with provisioned_postgres("huginn_attribute_impact") as url:
        yield url


def test_fill_impacts_and_alias_exclusions_preserve_all_stored_rows(
    impact_database_url,
):
    with psycopg.connect(impact_database_url) as connection:
        company_id, stable_id = _seed_company(connection, event_at=NOW)
        connection.execute(
            "UPDATE gold.company SET business_sector=NULL,company_scale=NULL,country='USA' WHERE id=%s",
            (company_id,),
        )
        connection.execute(
            "UPDATE bronze.api_ingest SET payload=payload || %s::jsonb WHERE source='yc' AND stable_id=%s",
            (
                '{"team_size":0,"industries":["B2B"],"all_locations":"San Francisco, CA, USA"}',
                stable_id,
            ),
        )
    _reconcile(impact_database_url)
    repository = PostgresAssessmentRepository(impact_database_url)
    target = CompiledCriteria(("B2B",), ("0-10",), ("USA",), (), (), ())
    excluded = CompiledCriteria(
        ("B2B",), ("0-10",), ("USA",), (), (), ("United States",)
    )
    windows = {
        "inclusive_boundary": SignalWindow(NOW, NOW),
        "after_event": SignalWindow(
            NOW + timedelta(microseconds=1), NOW + timedelta(days=1)
        ),
    }
    with psycopg.connect(impact_database_url) as connection:
        before = _stored_rows(connection)
    result = run_assessment(
        repository, {"positive": target, "alias_exclusion": excluded}, windows
    )
    impacts = {
        (row["criteria"], row["window"]): row for row in result.summary["comparisons"]
    }
    positive = impacts["positive", "inclusive_boundary"]
    assert (
        positive["before"],
        positive["after"],
        positive["newly_eligible"],
        positive["lost"],
    ) == (0, 1, 1, 0)
    assert impacts["positive", "after_event"]["after"] == 0
    excluded_result = impacts["alias_exclusion", "inclusive_boundary"]
    assert excluded_result["after"] == 1
    assert excluded_result["alias_counterfactual"] == {
        "after": 0,
        "newly_eligible_vs_fills": 0,
        "lost_vs_fills": 1,
    }
    assert result == run_assessment(
        repository, {"positive": target, "alias_exclusion": excluded}, windows
    )
    with psycopg.connect(impact_database_url) as connection:
        assert _stored_rows(connection) == before


def _stored_rows(connection):
    return {
        table: connection.execute(
            f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text"
        ).fetchall()
        for table in (
            "gold.company",
            "gold.company_signal",
            "silver.source_lifecycle_observation",
            "silver.source_context_snapshot",
            "silver.source_currentness",
            "operational.match",
            "operational.match_source_evidence",
        )
    }
