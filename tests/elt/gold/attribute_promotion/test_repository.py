"""Disposable PostgreSQL coverage for the read-only assessment adapter."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from huginn.elt.gold.attribute_promotion.models import CompanyAttributes
from huginn.elt.gold.attribute_promotion.repository import PostgresAssessmentRepository
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow
from huginn.matchmaking.persistence.repositories.sql.candidates import (
    SqlCandidateRepository,
)
from tests.matchmaking.test_evidence_integration import (
    NOW,
    _criteria,
    _reconcile,
    _scratch_database,
    _seed_company,
)
from tests.postgres_harness import provisioned_postgres


@pytest.fixture(scope="module")
def assessment_database_url():
    with provisioned_postgres("huginn_attribute_assessment") as url:
        yield url


@pytest.fixture
def scratch_url(assessment_database_url: str):
    with _scratch_database(assessment_database_url) as url:
        yield url


def test_snapshot_is_deterministic_complete_and_uses_current_guarded_evidence(
    scratch_url: str,
):
    with psycopg.connect(scratch_url) as connection:
        first, _ = _seed_company(connection, event_at=NOW - timedelta(days=1))
        no_event, _ = _seed_company(connection, event_at=None, industry="Other")
    _reconcile(scratch_url)
    repository = PostgresAssessmentRepository(scratch_url)

    snapshot = repository.read_snapshot()
    limited = repository.read_snapshot(limit=1)
    assert snapshot.companies == tuple(
        sorted(snapshot.companies, key=lambda company: company.company_id)
    )
    assert len(snapshot.companies) == 2
    assert snapshot.scope == "all_companies"
    assert limited.companies == snapshot.companies[:1]
    assert limited.scope == "first_1_companies_by_uuid"
    assert {fact.company_id for fact in limited.facts} <= {
        limited.companies[0].company_id
    }
    assert {fact.company_id for fact in snapshot.facts} == {first, no_event}
    assert any(
        fact.company_id == no_event and fact.occurred_at is None
        for fact in snapshot.facts
    )
    assert all(fact.raw_token and fact.resolution_token for fact in snapshot.facts)
    assert all(fact.source_fields.startswith("{") for fact in snapshot.facts)


def test_snapshot_rejects_mutation_and_invalid_limits(scratch_url: str):
    repository = PostgresAssessmentRepository(scratch_url)
    for invalid in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            repository.read_snapshot(invalid)  # type: ignore[arg-type]

    with psycopg.connect(scratch_url) as connection:
        connection.execute("BEGIN TRANSACTION READ ONLY")
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute("DELETE FROM gold.company")
        connection.rollback()


class _ReadOnlyProbeConnection:
    """Probe real PostgreSQL transaction state after adapter reads."""

    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def transaction(self):
        return self.connection.transaction()

    def execute(self, statement, *params):
        cursor = self.connection.execute(statement, *params)
        if (
            "FROM gold.company" in statement
            or "FROM gold.current_source_evidence" in statement
        ):
            assert (
                self.connection.execute(
                    "SELECT current_setting('transaction_read_only')"
                ).fetchone()[0]
                == "on"
            )
            self.connection.execute("SAVEPOINT adapter_readonly_probe")
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                self.connection.execute(
                    "INSERT INTO gold.company(domain,name) VALUES (%s,%s)",
                    (f"readonly-{uuid4().hex}.test", "Must be rejected"),
                )
            self.connection.execute("ROLLBACK TO SAVEPOINT adapter_readonly_probe")
            self.connection.execute("RELEASE SAVEPOINT adapter_readonly_probe")
        return cursor


def test_adapter_reads_and_rejects_writes_inside_same_read_only_transaction(
    scratch_url: str,
):
    repository = PostgresAssessmentRepository(
        scratch_url,
        connect=lambda url: _ReadOnlyProbeConnection(
            psycopg.connect(url, connect_timeout=5)
        ),
    )
    assert repository.read_snapshot().companies == ()


def test_restricted_select_role_can_read_assessment_snapshot(scratch_url: str):
    role = f"attribute_reader_{uuid4().hex[:12]}"
    with psycopg.connect(scratch_url) as connection:
        _seed_company(connection, event_at=NOW - timedelta(days=1))
    _reconcile(scratch_url)
    with psycopg.connect(scratch_url) as connection:
        connection.execute(
            psycopg.sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'reader-pass'").format(
                psycopg.sql.Identifier(role)
            )
        )
        connection.execute(f"GRANT USAGE ON SCHEMA gold,silver TO {role}")
        connection.execute(
            f"GRANT SELECT (id,business_sector,company_scale,country) ON gold.company TO {role}"
        )
        connection.execute(
            f"GRANT SELECT (company_id,source,source_stable_id,observation_id,occurred_at) "
            f"ON gold.current_source_evidence TO {role}"
        )
        connection.execute(
            f"GRANT SELECT (id,company_id,source,stable_id,snapshot_id,raw_token,"
            f"resolution_token,context_version,policy_version) "
            f"ON silver.source_lifecycle_observation TO {role}"
        )
        connection.execute(
            f"GRANT SELECT (id,source,stable_id,parser_version,source_fields) "
            f"ON silver.source_context_snapshot TO {role}"
        )
    values = conninfo_to_dict(scratch_url)
    values.update(user=role, password="reader-pass")
    try:
        snapshot = PostgresAssessmentRepository(make_conninfo(**values)).read_snapshot()
        assert len(snapshot.companies) == 1
        assert len(snapshot.facts) == 1
    finally:
        with psycopg.connect(scratch_url) as connection:
            connection.execute(
                psycopg.sql.SQL("DROP OWNED BY {}").format(psycopg.sql.Identifier(role))
            )
            connection.execute(
                psycopg.sql.SQL("DROP ROLE {}").format(psycopg.sql.Identifier(role))
            )


def test_snapshot_fails_closed_when_guard_schema_is_missing(
    scratch_url: str,
):
    with psycopg.connect(scratch_url) as connection:
        connection.execute("DROP VIEW gold.current_source_evidence")
    with pytest.raises(psycopg.errors.UndefinedTable):
        PostgresAssessmentRepository(scratch_url).read_snapshot()


def test_counterfactual_candidate_query_matches_real_matcher_and_uses_frozen_overrides(
    scratch_url: str,
):
    with psycopg.connect(scratch_url) as connection:
        first, _ = _seed_company(connection, event_at=NOW - timedelta(days=1))
        second, _ = _seed_company(
            connection, event_at=NOW - timedelta(days=1), industry="Other"
        )
        connection.execute(
            "UPDATE gold.company SET business_sector=ARRAY[' SaAs '] WHERE id=%s",
            (first,),
        )
        connection.execute(
            "UPDATE gold.company SET business_sector=%s WHERE id=%s",
            (["SaaS\t"], second),
        )
    _reconcile(scratch_url)
    repository = PostgresAssessmentRepository(scratch_url)
    snapshot = repository.read_snapshot()
    window = SignalWindow(NOW - timedelta(days=5), NOW)
    with psycopg.connect(scratch_url) as connection:
        actual = SqlCandidateRepository(connection).find_candidates(_criteria(), window)
        connection.rollback()
    assert (
        repository.candidate_ids(snapshot, snapshot.companies, _criteria(), window)
        == tuple(row.company_id for row in actual)
        == (first,)
    )

    criterion_cases = (
        _criteria(),
        CompiledCriteria(
            industries=(" SaaS ", "OTHER"),
            company_sizes=("0-10", "11-100"),
            countries=(" GERMANY ",),
            excluded_company_ids=(),
            excluded_industries=(),
            excluded_countries=(),
        ),
        CompiledCriteria(
            industries=("saas",),
            company_sizes=("0-10",),
            countries=("germany",),
            excluded_company_ids=(),
            excluded_industries=(" SaaS ",),
            excluded_countries=(),
        ),
        CompiledCriteria(
            industries=("saas",),
            company_sizes=("0-10",),
            countries=("germany",),
            excluded_company_ids=(first,),
            excluded_industries=(),
            excluded_countries=(),
        ),
        CompiledCriteria(
            industries=("saas",),
            company_sizes=("0-10",),
            countries=("germany",),
            excluded_company_ids=(),
            excluded_industries=(),
            excluded_countries=("GERMANY",),
        ),
    )
    window_cases = (
        window,
        SignalWindow(NOW - timedelta(days=1), NOW),
        SignalWindow(NOW - timedelta(days=1) + timedelta(microseconds=1), NOW),
    )
    for criteria in criterion_cases:
        for candidate_window in window_cases:
            with psycopg.connect(scratch_url) as connection:
                matched = SqlCandidateRepository(connection).find_candidates(
                    criteria, candidate_window
                )
                connection.rollback()
            assert repository.candidate_ids(
                snapshot, snapshot.companies, criteria, candidate_window
            ) == tuple(row.company_id for row in matched)

    changed = tuple(
        CompanyAttributes(
            company_id=company.company_id,
            business_sector=("SaaS",)
            if company.company_id == second
            else company.business_sector,
            company_scale=company.company_scale,
            country=company.country,
        )
        for company in snapshot.companies
    )
    # This reads only supplied frozen values, even after Gold changes.
    with psycopg.connect(scratch_url) as connection:
        connection.execute(
            "UPDATE gold.company SET business_sector=ARRAY['Different'] WHERE id=%s",
            (second,),
        )
    assert repository.candidate_ids(snapshot, changed, _criteria(), window) == tuple(
        sorted((first, second))
    )


@pytest.mark.parametrize("drift", ["raw", "resolution", "gold_company"])
def test_current_view_omits_stale_source_evidence(scratch_url: str, drift: str):
    with psycopg.connect(scratch_url) as connection:
        company_id, stable_id = _seed_company(
            connection, event_at=NOW - timedelta(days=1)
        )
        other_company_id, _ = _seed_company(connection, event_at=None, industry="Other")
    _reconcile(scratch_url)
    repository = PostgresAssessmentRepository(scratch_url)
    assert any(
        fact.company_id == company_id for fact in repository.read_snapshot().facts
    )
    with psycopg.connect(scratch_url) as connection:
        if drift == "raw":
            connection.execute(
                "UPDATE bronze.api_ingest SET payload=jsonb_set(payload,'{one_liner}',to_jsonb('changed'::text)) "
                "WHERE source='yc' AND stable_id=%s",
                (stable_id,),
            )
        elif drift == "resolution":
            connection.execute(
                "UPDATE silver.resolved_signals SET resolved_company_key=%s "
                "WHERE source='yc' AND source_stable_id=%s",
                (f"{other_company_id.hex}.other.test", stable_id),
            )
        else:
            connection.execute(
                "UPDATE gold.company_signal SET company_id=%s "
                "WHERE source='yc' AND source_stable_id=%s",
                (other_company_id, stable_id),
            )
    assert not any(
        fact.company_id == company_id for fact in repository.read_snapshot().facts
    )


def test_withdrawn_lifecycle_fact_is_removed_from_assessment_snapshot(
    scratch_url: str,
):
    with psycopg.connect(scratch_url) as connection:
        company_id, stable_id = _seed_company(
            connection, event_at=NOW - timedelta(days=1)
        )
    _reconcile(scratch_url)
    repository = PostgresAssessmentRepository(scratch_url)
    assert any(
        fact.company_id == company_id for fact in repository.read_snapshot().facts
    )

    with psycopg.connect(scratch_url) as connection:
        connection.execute(
            "UPDATE bronze.api_ingest SET payload=jsonb_set(payload,'{status}','\"Inactive\"') "
            "WHERE source='yc' AND stable_id=%s",
            (stable_id,),
        )
    _reconcile(scratch_url)
    assert not any(
        fact.company_id == company_id for fact in repository.read_snapshot().facts
    )
