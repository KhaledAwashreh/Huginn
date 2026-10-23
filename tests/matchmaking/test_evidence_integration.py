"""Disposable PostgreSQL checks for Match creation evidence boundaries."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from huginn.elt.silver.currentness.repository import PostgresLifecycleRepository
from huginn.elt.silver.currentness.runner import run_reconcile
from huginn.matchmaking.application.requests.matchmaking_request import (
    MatchmakingRequest,
)
from huginn.matchmaking.application.services.matchmaking_service import (
    MatchmakingService,
)
from huginn.matchmaking.domain.errors.criteria import CriteriaIssue
from huginn.matchmaking.domain.services.icp_evaluator import compile_icp
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow
from huginn.matchmaking.persistence.errors.database import (
    DatabaseOperationError,
    DataIntegrityError,
)
from huginn.matchmaking.persistence.repositories.sql.candidates import (
    SqlCandidateRepository,
)
from huginn.matchmaking.persistence.repositories.sql.matches import SqlMatchRepository
from huginn.matchmaking.persistence.unit_of_work.sql import (
    SqlMatchmakingUnitOfWork,
    check_readiness,
)
from tests.postgres_harness import SCHEMA_DIR, SCHEMA_FILES, provisioned_postgres

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def base_evidence_database_url() -> Iterator[str]:
    with provisioned_postgres("huginn_match_evidence") as url:
        yield url


@contextlib.contextmanager
def _scratch_database(database_url: str) -> Iterator[str]:
    name = f"huginn_evidence_{uuid4().hex[:12]}"
    admin = conninfo_to_dict(database_url)
    admin["dbname"] = "postgres"
    admin_url = make_conninfo(**admin)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    scratch = conninfo_to_dict(database_url)
    scratch["dbname"] = name
    scratch_url = make_conninfo(**scratch)
    try:
        with psycopg.connect(scratch_url, autocommit=True) as connection:
            for filename in SCHEMA_FILES:
                connection.execute((SCHEMA_DIR / filename).read_text())
        yield scratch_url
    finally:
        with (
            contextlib.suppress(Exception),
            psycopg.connect(admin_url, autocommit=True) as connection,
        ):
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                )
            )


@pytest.fixture
def evidence_database_url(base_evidence_database_url: str) -> Iterator[str]:
    with _scratch_database(base_evidence_database_url) as url:
        yield url


def _seed_company(
    connection: psycopg.Connection,
    *,
    event_at: datetime | None,
    industry: str = "SaaS",
    company_id: UUID | None = None,
    hiring: bool = False,
    status: str = "Active",
) -> tuple[UUID, str]:
    company_id = company_id or uuid4()
    domain = f"{company_id.hex}.example.test"
    connection.execute(
        "INSERT INTO gold.company(id,domain,name,country,business_sector,company_scale) "
        "VALUES (%s,%s,'Evidence fixture','Germany',%s,'0-10')",
        (company_id, domain, [industry]),
    )
    return _seed_source(
        connection,
        company_id=company_id,
        domain=domain,
        event_at=event_at,
        hiring=hiring,
        status=status,
    )


def _seed_source(
    connection: psycopg.Connection,
    *,
    company_id: UUID,
    domain: str,
    event_at: datetime | None,
    hiring: bool,
    status: str = "Active",
    stable_id: str | None = None,
) -> tuple[UUID, str]:
    stable_id = stable_id or f"evidence-{uuid4().hex}"
    payload: dict[str, object] = {
        "id": stable_id,
        "slug": stable_id,
        "name": "Evidence fixture",
        "website": f"https://{domain}",
        "status": status,
        "isHiring": hiring,
        "one_liner": "A captured directory record for integration tests.",
    }
    if event_at is not None:
        payload["launched_at"] = event_at.timestamp()
    connection.execute(
        "INSERT INTO bronze.api_ingest(source,stable_id,payload,content_hash,run_id) "
        "VALUES ('yc',%s,%s,'evidence-seed',%s)",
        (stable_id, psycopg.types.json.Jsonb(payload), uuid4()),
    )
    connection.execute(
        "INSERT INTO silver.resolved_signals "
        "(source,source_stable_id,resolved_company_key,company_name_raw,signal_type,key_derivation) "
        "VALUES ('yc',%s,%s,'Evidence fixture','other','domain_normalized')",
        (stable_id, domain),
    )
    connection.execute(
        "INSERT INTO gold.company_signal(company_id,source,source_stable_id,signal_type,occurred_at) "
        "VALUES (%s,'yc',%s,'other',%s)",
        (company_id, stable_id, event_at or NOW),
    )
    return company_id, stable_id


def _reconcile(database_url: str) -> None:
    report = run_reconcile("yc", PostgresLifecycleRepository(database_url))
    assert report["status"] == "complete", report


def _user_and_strategy(
    connection: psycopg.Connection, *, industry: str = "SaaS"
) -> UUID:
    account_id = connection.execute(
        "INSERT INTO operational.accounts(username,password_hash) "
        "VALUES (%s,'hash') RETURNING id",
        (f"evidence-{uuid4().hex}",),
    ).fetchone()[0]
    user_id = connection.execute(
        """INSERT INTO operational.users
             (account_id,first_name,last_name,email,phone_number,country_of_residence)
           VALUES (%s,'Evidence','Tester',%s,'1','DE') RETURNING id""",
        (account_id, f"{account_id}@example.test"),
    ).fetchone()[0]
    offering_id, icp_id = uuid4(), uuid4()
    connection.execute(
        "INSERT INTO operational.service_offerings(id,user_id,name,description) "
        "VALUES (%s,%s,'Offer','Description')",
        (offering_id, user_id),
    )
    connection.execute(
        """INSERT INTO operational.ideal_client_profiles
             (id,user_id,name,industries,company_sizes,geographies,exclusions)
           VALUES (%s,%s,'ICP',%s,'[{"band":"0-10"}]',
                   '[{"kind":"country","value":"Germany"}]','[]')""",
        (icp_id, user_id, psycopg.types.json.Jsonb([{"name": industry}])),
    )
    connection.execute(
        """INSERT INTO operational.client_discovery_strategies
             (user_id,name,service_offering_id,ideal_client_profile_id,is_active)
           VALUES (%s,'Strategy',%s,%s,TRUE)""",
        (user_id, offering_id, icp_id),
    )
    return user_id


class _Clock:
    def now(self) -> datetime:
        return NOW


def _execute(database_url: str, user_id: UUID, cutoff: datetime) -> object:
    service = MatchmakingService(
        lambda: SqlMatchmakingUnitOfWork(database_url), _Clock()
    )
    return service.execute(MatchmakingRequest(user_id, cutoff, NOW))


def _criteria(industry: str = "SaaS") -> CompiledCriteria:
    result = compile_icp(
        industries=({"name": industry},),
        company_sizes=({"band": "0-10"},),
        geographies=({"kind": "country", "value": "Germany"},),
        exclusions=(),
    )
    assert not isinstance(result, CriteriaIssue)
    return result


def test_new_match_captures_distinct_directory_observations_and_exact_window(
    evidence_database_url: str,
):
    cutoff = datetime(2026, 10, 1, 11, 0, 0, 123456, tzinfo=UTC)
    event_times = (cutoff, NOW)
    with psycopg.connect(evidence_database_url) as connection:
        company_id, _ = _seed_company(connection, event_at=event_times[0])
        _seed_source(
            connection,
            company_id=company_id,
            domain=connection.execute(
                "SELECT domain FROM gold.company WHERE id=%s", (company_id,)
            ).fetchone()[0],
            event_at=event_times[1],
            hiring=False,
        )
        user_id = _user_and_strategy(connection)
    _reconcile(evidence_database_url)

    response = _execute(evidence_database_url, user_id, cutoff)
    assert response.unique_candidates_count == 1
    assert len(response.created_matches) == 1
    assert response.created_matches[0].company_id == company_id

    with psycopg.connect(evidence_database_url) as connection:
        evidence = connection.execute(
            """SELECT e.observation_id,e.cutoff,e.as_of,v.evidence_kind,v.hiring_state
               FROM operational.match_source_evidence e
               JOIN gold.current_source_evidence v USING (observation_id)
               WHERE e.match_id=%s ORDER BY e.observation_id""",
            (response.created_matches[0].id,),
        ).fetchall()
    assert len(evidence) == 2
    assert [row[0] for row in evidence] == sorted(row[0] for row in evidence)
    assert all(row[1:3] == (cutoff, NOW) for row in evidence)
    assert all(row[3:] == ("directory_context", "false") for row in evidence)


@pytest.mark.parametrize("drift", ["raw", "resolution", "gold_company", "withdrawn"])
def test_stale_or_withdrawn_source_evidence_is_not_a_candidate(
    evidence_database_url: str, drift: str
):
    with psycopg.connect(evidence_database_url) as connection:
        company_id, stable_id = _seed_company(
            connection, event_at=NOW - timedelta(days=1)
        )
        other_company_id, _ = _seed_company(connection, event_at=None, industry="Other")
    _reconcile(evidence_database_url)

    with psycopg.connect(evidence_database_url) as connection:
        if drift == "raw":
            connection.execute(
                "UPDATE bronze.api_ingest SET payload=jsonb_set(payload,'{one_liner}','\"changed\"') "
                "WHERE source='yc' AND stable_id=%s",
                (stable_id,),
            )
        elif drift == "resolution":
            connection.execute(
                "UPDATE silver.resolved_signals SET resolved_company_key=%s "
                "WHERE source='yc' AND source_stable_id=%s",
                (f"{uuid4().hex}.other.test", stable_id),
            )
        elif drift == "gold_company":
            connection.execute(
                "UPDATE gold.company_signal SET company_id=%s "
                "WHERE source='yc' AND source_stable_id=%s",
                (other_company_id, stable_id),
            )
        else:
            connection.execute(
                "UPDATE bronze.api_ingest SET payload=jsonb_set(payload,'{status}','\"Inactive\"') "
                "WHERE source='yc' AND stable_id=%s",
                (stable_id,),
            )
    if drift == "withdrawn":
        _reconcile(evidence_database_url)

    with psycopg.connect(evidence_database_url) as connection:
        candidates = SqlCandidateRepository(connection).find_candidates(
            _criteria(), SignalWindow(NOW - timedelta(days=10), NOW)
        )
        connection.rollback()
    assert company_id not in {candidate.company_id for candidate in candidates}


def test_null_and_out_of_window_event_times_are_excluded(evidence_database_url: str):
    cutoff = NOW - timedelta(days=7)
    with psycopg.connect(evidence_database_url) as connection:
        null_company, _ = _seed_company(connection, event_at=None)
        old_company, _ = _seed_company(
            connection, event_at=cutoff - timedelta(microseconds=1)
        )
        current_company, _ = _seed_company(connection, event_at=cutoff)
    _reconcile(evidence_database_url)
    with psycopg.connect(evidence_database_url) as connection:
        candidates = SqlCandidateRepository(connection).find_candidates(
            _criteria(), SignalWindow(cutoff, NOW)
        )
        connection.rollback()
    assert [candidate.company_id for candidate in candidates] == [current_company]
    assert null_company not in {candidate.company_id for candidate in candidates}
    assert old_company not in {candidate.company_id for candidate in candidates}


def test_bad_cross_company_proof_rolls_back_all_matches_and_links(
    evidence_database_url: str,
):
    with psycopg.connect(evidence_database_url) as connection:
        first, _ = _seed_company(connection, event_at=NOW - timedelta(days=1))
        second, _ = _seed_company(connection, event_at=NOW - timedelta(days=1))
        user_id = _user_and_strategy(connection)
    _reconcile(evidence_database_url)
    window = SignalWindow(NOW - timedelta(days=5), NOW)
    with psycopg.connect(evidence_database_url) as connection:
        selected = SqlCandidateRepository(connection).find_candidates(
            _criteria(), window
        )
        evidence_by_company = {row.company_id: row.observation_ids for row in selected}
        connection.rollback()
    assert {first, second} == set(evidence_by_company)

    with (
        pytest.raises(DatabaseOperationError),
        SqlMatchmakingUnitOfWork(evidence_database_url) as uow,
    ):
        assert uow.matches.insert_if_absent(
            user_id,
            first,
            observation_ids=evidence_by_company[first],
            window=window,
        )
        uow.matches.insert_if_absent(
            user_id,
            second,
            observation_ids=evidence_by_company[first],
            window=window,
        )
        uow.commit()
    with psycopg.connect(evidence_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.match WHERE user_id=%s", (user_id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.match_source_evidence"
            ).fetchone()[0]
            == 0
        )


def test_existing_legacy_match_is_not_backfilled_or_changed(evidence_database_url: str):
    with psycopg.connect(evidence_database_url) as connection:
        company_id, _ = _seed_company(connection, event_at=NOW - timedelta(days=1))
        user_id = _user_and_strategy(connection)
        legacy = connection.execute(
            "INSERT INTO operational.match(user_id,company_id,status,notes) "
            "VALUES (%s,%s,'dismissed','keep this') RETURNING id,created_at,updated_at",
            (user_id, company_id),
        ).fetchone()
    _reconcile(evidence_database_url)

    response = _execute(evidence_database_url, user_id, NOW - timedelta(days=5))
    assert response.created_matches == ()
    assert response.existing_matches_skipped_count == 1
    with psycopg.connect(evidence_database_url) as connection:
        assert connection.execute(
            "SELECT id,status,notes,created_at,updated_at FROM operational.match "
            "WHERE user_id=%s AND company_id=%s",
            (user_id, company_id),
        ).fetchone() == (legacy[0], "dismissed", "keep this", legacy[1], legacy[2])
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.match_source_evidence WHERE match_id=%s",
                (legacy[0],),
            ).fetchone()[0]
            == 0
        )


def test_existing_captured_match_keeps_its_original_evidence(
    evidence_database_url: str,
):
    with psycopg.connect(evidence_database_url) as connection:
        company_id, _ = _seed_company(connection, event_at=NOW - timedelta(days=1))
        domain = connection.execute(
            "SELECT domain FROM gold.company WHERE id=%s", (company_id,)
        ).fetchone()[0]
        user_id = _user_and_strategy(connection)
    _reconcile(evidence_database_url)

    created = _execute(evidence_database_url, user_id, NOW - timedelta(days=5))
    assert len(created.created_matches) == 1
    match_id = created.created_matches[0].id
    with psycopg.connect(evidence_database_url) as connection:
        original = connection.execute(
            "SELECT observation_id,cutoff,as_of FROM operational.match_source_evidence "
            "WHERE match_id=%s ORDER BY observation_id",
            (match_id,),
        ).fetchall()
        _seed_source(
            connection,
            company_id=company_id,
            domain=domain,
            event_at=NOW,
            hiring=False,
        )
    _reconcile(evidence_database_url)

    repeated = _execute(evidence_database_url, user_id, NOW - timedelta(days=5))
    assert repeated.created_matches == ()
    assert repeated.existing_matches_skipped_count == 1
    with psycopg.connect(evidence_database_url) as connection:
        retained = connection.execute(
            "SELECT observation_id,cutoff,as_of FROM operational.match_source_evidence "
            "WHERE match_id=%s ORDER BY observation_id",
            (match_id,),
        ).fetchall()
    assert retained == original


def test_repeatable_read_snapshot_preserves_selected_proof_after_withdrawal(
    evidence_database_url: str,
):
    with psycopg.connect(evidence_database_url) as connection:
        company_id, stable_id = _seed_company(
            connection, event_at=NOW - timedelta(days=1)
        )
        user_id = _user_and_strategy(connection)
    _reconcile(evidence_database_url)
    window = SignalWindow(NOW - timedelta(days=5), NOW)

    with SqlMatchmakingUnitOfWork(evidence_database_url) as uow:
        selected = uow.candidates.find_candidates(_criteria(), window)
        assert len(selected) == 1
        with psycopg.connect(evidence_database_url) as writer:
            writer.execute(
                "UPDATE bronze.api_ingest SET payload=jsonb_set(payload,'{status}','\"Inactive\"') "
                "WHERE source='yc' AND stable_id=%s",
                (stable_id,),
            )
        _reconcile(evidence_database_url)
        match = uow.matches.insert_if_absent(
            user_id,
            company_id,
            observation_ids=selected[0].observation_ids,
            window=window,
        )
        assert match is not None
        uow.commit()

    with psycopg.connect(evidence_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.match_source_evidence WHERE match_id=%s",
                (match.id,),
            ).fetchone()[0]
            == 1
        )
        candidates = SqlCandidateRepository(connection).find_candidates(
            _criteria(), window
        )
        connection.rollback()
    assert candidates == ()


def test_invalid_evidence_is_rejected_before_writes_and_autocommit_is_rejected(
    evidence_database_url: str,
):
    with psycopg.connect(evidence_database_url) as connection:
        company_id, _ = _seed_company(connection, event_at=NOW - timedelta(days=1))
        user_id = _user_and_strategy(connection)
    _reconcile(evidence_database_url)
    window = SignalWindow(NOW - timedelta(days=5), NOW)
    with psycopg.connect(evidence_database_url) as connection:
        repository = SqlMatchRepository(connection)
        with pytest.raises(DataIntegrityError):
            repository.insert_if_absent(
                user_id, company_id, observation_ids=(), window=window
            )
        with pytest.raises(DataIntegrityError):
            repository.insert_if_absent(
                user_id,
                company_id,
                observation_ids=("not-a-uuid",),  # type: ignore[arg-type]
                window=window,
            )
        connection.rollback()
    with (
        psycopg.connect(evidence_database_url, autocommit=True) as connection,
        pytest.raises(DataIntegrityError),
    ):
        SqlMatchRepository(connection).insert_if_absent(
            user_id,
            company_id,
            observation_ids=(uuid4(),),
            window=window,
        )
    with psycopg.connect(evidence_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.match WHERE user_id=%s", (user_id,)
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("missing", ["view", "history", "insert_grant"])
def test_readiness_fails_closed_without_guarded_evidence_dependencies(
    evidence_database_url: str, missing: str
):
    with _scratch_database(evidence_database_url) as scratch_url:
        if missing == "view":
            statement = "DROP VIEW gold.current_source_evidence"
        elif missing == "history":
            statement = "DROP TABLE operational.match_source_evidence"
        else:
            statement = None
        if statement:
            with psycopg.connect(scratch_url) as connection:
                connection.execute(statement)
        else:
            with psycopg.connect(scratch_url) as connection:
                connection.execute(
                    "CREATE ROLE evidence_reader LOGIN PASSWORD 'reader-pass'"
                )
                connection.execute(
                    "GRANT USAGE ON SCHEMA operational,gold TO evidence_reader"
                )
                connection.execute(
                    "GRANT SELECT ON ALL TABLES IN SCHEMA operational,gold TO evidence_reader"
                )
        if missing == "insert_grant":
            values = conninfo_to_dict(scratch_url)
            values.update(user="evidence_reader", password="reader-pass")
            scratch_url = make_conninfo(**values)
        with pytest.raises(DatabaseOperationError):
            check_readiness(scratch_url)


def test_restricted_runtime_role_passes_readiness_and_captures_evidence(
    evidence_database_url: str,
):
    with _scratch_database(evidence_database_url) as scratch_url:
        with psycopg.connect(scratch_url) as connection:
            company_id, _ = _seed_company(
                connection, event_at=NOW - timedelta(days=1), hiring=False
            )
            user_id = _user_and_strategy(connection)
        _reconcile(scratch_url)

        with psycopg.connect(scratch_url) as administrator:
            administrator.execute(
                "CREATE ROLE evidence_runtime LOGIN PASSWORD 'runtime-test-password' "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            )
            administrator.execute(
                "GRANT USAGE ON SCHEMA operational,gold TO evidence_runtime"
            )
            administrator.execute(
                """GRANT SELECT (id,status) ON operational.accounts TO evidence_runtime;
                   GRANT SELECT (id,account_id) ON operational.users TO evidence_runtime;
                   GRANT SELECT (id,user_id,name,service_offering_id,ideal_client_profile_id,is_active)
                     ON operational.client_discovery_strategies TO evidence_runtime;
                   GRANT SELECT (id,user_id) ON operational.service_offerings TO evidence_runtime;
                   GRANT SELECT (id,user_id,industries,company_sizes,geographies,exclusions)
                     ON operational.ideal_client_profiles TO evidence_runtime;
                   GRANT SELECT (id,business_sector,company_scale,country)
                     ON gold.company TO evidence_runtime;
                   GRANT SELECT (company_id,observation_id,occurred_at)
                     ON gold.current_source_evidence TO evidence_runtime;
                   GRANT SELECT (id,user_id,company_id,status,notes,created_at,updated_at),
                               INSERT (user_id,company_id,status,notes)
                     ON operational.match TO evidence_runtime;
                   GRANT SELECT (match_id,observation_id,cutoff,as_of),
                               INSERT (match_id,observation_id,cutoff,as_of)
                     ON operational.match_source_evidence TO evidence_runtime;"""
            )
        values = conninfo_to_dict(scratch_url)
        values.update(user="evidence_runtime", password="runtime-test-password")
        runtime_url = make_conninfo(**values)

        check_readiness(runtime_url)
        response = _execute(runtime_url, user_id, NOW - timedelta(days=5))
        assert len(response.created_matches) == 1
        assert response.created_matches[0].company_id == company_id
        with psycopg.connect(scratch_url) as administrator:
            assert (
                administrator.execute(
                    "SELECT count(*) FROM operational.match_source_evidence WHERE match_id=%s",
                    (response.created_matches[0].id,),
                ).fetchone()[0]
                == 1
            )
            assert not administrator.execute(
                "SELECT has_table_privilege('evidence_runtime','gold.company_signal','SELECT')"
            ).fetchone()[0]
            assert not administrator.execute(
                "SELECT has_schema_privilege('evidence_runtime','silver','USAGE')"
            ).fetchone()[0]
            assert not administrator.execute(
                "SELECT has_schema_privilege('evidence_runtime','bronze','USAGE')"
            ).fetchone()[0]
