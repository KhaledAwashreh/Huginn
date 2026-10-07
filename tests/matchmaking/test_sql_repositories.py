"""PostgreSQL 16 behavior for the matchmaking SQL adapters."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from huginn.matchmaking.application.read_models.user_availability import (
    UserAvailability,
)
from huginn.matchmaking.domain.entities.match import MatchStatus
from huginn.matchmaking.domain.errors.criteria import CriteriaIssue, CriteriaIssueReason
from huginn.matchmaking.domain.services.icp_evaluator import compile_icp
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow
from huginn.matchmaking.persistence.errors.database import (
    DataIntegrityError,
    RetryableTransactionError,
)
from huginn.matchmaking.persistence.repositories.sql.candidates import (
    SqlCandidateRepository,
)
from huginn.matchmaking.persistence.repositories.sql.configuration import (
    SqlConfigurationRepository,
)
from huginn.matchmaking.persistence.unit_of_work.sql import SqlMatchmakingUnitOfWork
from tests.postgres_harness import SCHEMA_DIR, SCHEMA_FILES


@contextmanager
def _scratch_database(database_url: str) -> Iterator[str]:
    name = f"huginn_match_sql_{uuid4().hex[:12]}"
    admin = conninfo_to_dict(database_url)
    admin["dbname"] = "postgres"
    admin_url = make_conninfo(**admin)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    scratch = conninfo_to_dict(database_url)
    scratch["dbname"] = name
    scratch_url = make_conninfo(**scratch)
    try:
        with psycopg.connect(scratch_url, autocommit=True) as conn:
            for filename in SCHEMA_FILES:
                conn.execute((SCHEMA_DIR / filename).read_text())
        yield scratch_url
    finally:
        with (
            contextlib.suppress(Exception),
            psycopg.connect(admin_url, autocommit=True) as conn,
        ):
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                )
            )


def _drop_checks(conn: psycopg.Connection, table: str) -> None:
    schema, relation = table.split(".")
    rows = conn.execute(
        "SELECT c.conname FROM pg_constraint AS c "
        "JOIN pg_class AS t ON t.oid=c.conrelid "
        "JOIN pg_namespace AS n ON n.oid=t.relnamespace "
        "WHERE n.nspname=%s AND t.relname=%s AND c.contype='c'",
        (schema, relation),
    ).fetchall()
    for (name,) in rows:
        conn.execute(
            sql.SQL("ALTER TABLE {}.{} DROP CONSTRAINT {}").format(
                sql.Identifier(schema), sql.Identifier(relation), sql.Identifier(name)
            )
        )


def _drop_foreign_keys(conn: psycopg.Connection, table: str) -> None:
    schema, relation = table.split(".")
    rows = conn.execute(
        "SELECT c.conname FROM pg_constraint AS c "
        "JOIN pg_class AS t ON t.oid=c.conrelid "
        "JOIN pg_namespace AS n ON n.oid=t.relnamespace "
        "WHERE n.nspname=%s AND t.relname=%s AND c.contype='f'",
        (schema, relation),
    ).fetchall()
    for (name,) in rows:
        conn.execute(
            sql.SQL("ALTER TABLE {}.{} DROP CONSTRAINT {}").format(
                sql.Identifier(schema), sql.Identifier(relation), sql.Identifier(name)
            )
        )


def _user(conn: psycopg.Connection, *, active: bool = True) -> tuple:
    account_id, user_id = uuid4(), uuid4()
    conn.execute(
        "INSERT INTO operational.accounts (id, username, password_hash, status) "
        "VALUES (%s, %s, 'hash', %s)",
        (account_id, f"match-{account_id}", "active" if active else "disabled"),
    )
    conn.execute(
        "INSERT INTO operational.users "
        "(id, account_id, first_name, last_name, email, phone_number, country_of_residence) "
        "VALUES (%s, %s, 'First', 'Last', %s, '1', 'US')",
        (user_id, account_id, f"{user_id}@example.test"),
    )
    return user_id, account_id


def _company(
    conn: psycopg.Connection,
    *,
    sectors: list[str] | None,
    size: str | None = "0-10",
    country: str | None = "Germany",
    signal_at: datetime | None = None,
) -> UUID:
    company_id = uuid4()
    conn.execute(
        "INSERT INTO gold.company (id, domain, name, business_sector, company_scale, country) "
        "VALUES (%s, %s, 'Company', %s, %s, %s)",
        (company_id, f"{company_id}.example.test", sectors, size, country),
    )
    if signal_at is not None:
        conn.execute(
            "INSERT INTO gold.company_signal "
            "(company_id, source, source_stable_id, signal_type, occurred_at) "
            "VALUES (%s, 'test', %s, 'other', %s)",
            (company_id, str(company_id), signal_at),
        )
    return company_id


def _signal(
    conn: psycopg.Connection,
    company_id: UUID,
    signal_type: str,
    occurred_at: datetime,
) -> None:
    conn.execute(
        "INSERT INTO gold.company_signal "
        "(company_id, source, source_stable_id, signal_type, occurred_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (company_id, f"test-{signal_type}", str(uuid4()), signal_type, occurred_at),
    )


def test_configuration_queries_are_user_scoped_and_validate_active_strategy_rows(
    integration_database_url: str,
):
    with psycopg.connect(integration_database_url) as conn:
        user_id, _account = _user(conn)
        other_user_id, _ = _user(conn)
        disabled_user_id, _ = _user(conn, active=False)
        offering_id, icp_id = uuid4(), uuid4()
        conn.execute(
            "INSERT INTO operational.service_offerings (id,user_id,name,description) "
            "VALUES (%s,%s,'Offer','Description')",
            (offering_id, user_id),
        )
        conn.execute(
            "INSERT INTO operational.ideal_client_profiles "
            "(id,user_id,name,industries,company_sizes,geographies,exclusions) "
            "VALUES (%s,%s,'Profile','[{\"name\":\"SaaS\"}]',"
            '\'[{"band":"0-10"}]\',\'[{"kind":"country","value":"Germany"}]\',\'[]\')',
            (icp_id, user_id),
        )
        conn.execute(
            "INSERT INTO operational.client_discovery_strategies "
            "(user_id,name,service_offering_id,ideal_client_profile_id,is_active) "
            "VALUES (%s,'Active strategy',%s,%s,TRUE),(%s,'Inactive strategy',%s,%s,FALSE)",
            (user_id, offering_id, icp_id, user_id, offering_id, icp_id),
        )
        conn.cursor().executemany(
            "INSERT INTO operational.client_discovery_strategies "
            "(user_id,name,service_offering_id,ideal_client_profile_id,is_active) "
            "VALUES (%s,%s,%s,%s,TRUE)",
            [(user_id, f"Target {index}", offering_id, icp_id) for index in range(101)],
        )
        other_offering, other_icp = uuid4(), uuid4()
        conn.execute(
            "INSERT INTO operational.service_offerings (id,user_id,name,description) "
            "VALUES (%s,%s,'Offer','Description')",
            (other_offering, other_user_id),
        )
        conn.execute(
            "INSERT INTO operational.ideal_client_profiles (id,user_id,name) "
            "VALUES (%s,%s,'Profile')",
            (other_icp, other_user_id),
        )
        conn.execute(
            "INSERT INTO operational.client_discovery_strategies "
            "(user_id,name,service_offering_id,ideal_client_profile_id,is_active) "
            "VALUES (%s,'Other user strategy',%s,%s,TRUE)",
            (other_user_id, other_offering, other_icp),
        )
        conn.commit()

    with psycopg.connect(integration_database_url) as conn:
        repository = SqlConfigurationRepository(conn)
        assert repository.user_availability(user_id) is UserAvailability.ACTIVE
        assert (
            repository.user_availability(disabled_user_id) is UserAvailability.DISABLED
        )
        assert repository.user_availability(uuid4()) is UserAvailability.MISSING
        strategies = repository.list_active_strategies(user_id)
        assert len(strategies) == 102
        active = next(value for value in strategies if value.name == "Active strategy")
        assert active.user_id == user_id
        assert active.industries == ({"name": "SaaS"},)
        conn.rollback()


def test_configuration_preserves_malformed_icp_json_for_safe_compiler_skips(
    integration_database_url: str,
):
    with _scratch_database(integration_database_url) as database_url:
        with psycopg.connect(database_url) as conn:
            _drop_checks(conn, "operational.ideal_client_profiles")
            user_id, _ = _user(conn)
            offering_id = uuid4()
            conn.execute(
                "INSERT INTO operational.service_offerings (id,user_id,name,description) "
                "VALUES (%s,%s,'Offer','Description')",
                (offering_id, user_id),
            )
            malformed_icps = (
                (
                    uuid4(),
                    json.dumps({"unexpected": "outer object"}),
                    json.dumps([{"band": "0-10"}]),
                ),
                (
                    uuid4(),
                    json.dumps([{"name": "SaaS", "extra": True}]),
                    json.dumps([{"band": "0-10"}]),
                ),
            )
            for icp_id, industries, sizes in malformed_icps:
                conn.execute(
                    "INSERT INTO operational.ideal_client_profiles "
                    "(id,user_id,name,industries,company_sizes,geographies,exclusions) "
                    "VALUES (%s,%s,'Profile',%s::jsonb,%s::jsonb,"
                    '\'[{"kind":"country","value":"Germany"}]\',\'[]\')',
                    (icp_id, user_id, industries, sizes),
                )
                conn.execute(
                    "INSERT INTO operational.client_discovery_strategies "
                    "(user_id,name,service_offering_id,ideal_client_profile_id,is_active) "
                    "VALUES (%s,'Malformed ICP',%s,%s,TRUE)",
                    (user_id, offering_id, icp_id),
                )
            conn.commit()

        with psycopg.connect(database_url) as conn:
            strategies = SqlConfigurationRepository(conn).list_active_strategies(
                user_id
            )
            conn.rollback()

        assert len(strategies) == 2
        results = [
            compile_icp(
                industries=strategy.industries,
                company_sizes=strategy.company_sizes,
                geographies=strategy.geographies,
                exclusions=strategy.exclusions,
            )
            for strategy in strategies
        ]
        assert results == [
            CriteriaIssue(CriteriaIssueReason.INVALID_ICP),
            CriteriaIssue(CriteriaIssueReason.INVALID_ICP),
        ]


def test_configuration_rejects_cross_owner_left_join_sentinels(
    integration_database_url: str,
):
    with _scratch_database(integration_database_url) as database_url:
        with psycopg.connect(database_url) as conn:
            _drop_foreign_keys(conn, "operational.client_discovery_strategies")
            first_user, _ = _user(conn)
            second_user, _ = _user(conn)
            refs = []
            for user_id in (first_user, second_user):
                offering_id, icp_id = uuid4(), uuid4()
                conn.execute(
                    "INSERT INTO operational.service_offerings (id,user_id,name,description) "
                    "VALUES (%s,%s,'Offer','Description')",
                    (offering_id, user_id),
                )
                conn.execute(
                    "INSERT INTO operational.ideal_client_profiles (id,user_id,name) "
                    "VALUES (%s,%s,'Profile')",
                    (icp_id, user_id),
                )
                refs.append((offering_id, icp_id))
            first_offering, first_icp = refs[0]
            second_offering, second_icp = refs[1]
            conn.execute(
                "INSERT INTO operational.client_discovery_strategies "
                "(user_id,name,service_offering_id,ideal_client_profile_id,is_active) "
                "VALUES (%s,'Foreign offering',%s,%s,TRUE),"
                "(%s,'Foreign ICP',%s,%s,TRUE)",
                (
                    first_user,
                    second_offering,
                    first_icp,
                    first_user,
                    first_offering,
                    second_icp,
                ),
            )
            conn.commit()

        with (
            psycopg.connect(database_url) as conn,
            pytest.raises(DataIntegrityError, match="Broken strategy reference"),
        ):
            SqlConfigurationRepository(conn).list_active_strategies(first_user)


def test_candidate_query_applies_all_dimensions_exclusions_and_inclusive_signal_window(
    integration_database_url: str,
):
    cutoff = datetime(2026, 10, 1, tzinfo=UTC)
    as_of = datetime(2026, 10, 7, tzinfo=UTC)
    with psycopg.connect(integration_database_url) as conn:
        accepted = _company(conn, sectors=["SaaS", "Unspecified"], signal_at=cutoff)
        accepted_as_of = _company(conn, sectors=["SaaS"], signal_at=as_of)
        excluded_company = _company(conn, sectors=["SaaS"], signal_at=cutoff)
        wrong_size = _company(conn, sectors=["SaaS"], size="11-100", signal_at=cutoff)
        wrong_country = _company(
            conn, sectors=["SaaS"], country="France", signal_at=cutoff
        )
        excluded_sector = _company(conn, sectors=["SaaS", "Gambling"], signal_at=as_of)
        too_early = _company(
            conn, sectors=["SaaS"], signal_at=cutoff - timedelta(microseconds=1)
        )
        too_late = _company(
            conn, sectors=["SaaS"], signal_at=as_of + timedelta(microseconds=1)
        )
        _ = wrong_size, wrong_country, excluded_sector, too_early, too_late
        conn.commit()

    criteria = CompiledCriteria(
        industries=("SaaS",),
        company_sizes=("0-10",),
        countries=("France", "Germany"),
        excluded_company_ids=(excluded_company,),
        excluded_industries=("Gambling",),
        excluded_countries=("France",),
    )
    with psycopg.connect(integration_database_url) as conn:
        candidates = SqlCandidateRepository(conn).find_candidates(
            criteria, SignalWindow(cutoff, as_of)
        )
        conn.rollback()
    assert tuple(candidate.company_id for candidate in candidates) == tuple(
        sorted((accepted, accepted_as_of), key=lambda company_id: company_id.int)
    )


def test_candidate_query_normalizes_text_and_accepts_any_industry_size_country(
    integration_database_url: str,
):
    cutoff, as_of = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 7, tzinfo=UTC)
    industry = f"Matchmaking{uuid4().hex}"
    veto_industry = f"Veto{uuid4().hex}"
    with psycopg.connect(integration_database_url) as conn:
        qualified = _company(
            conn,
            sectors=[f"  {industry.upper()}  ", " FinTech "],
            size="11-100",
            country="  gErMaNy  ",
            signal_at=as_of,
        )
        _company(
            conn,
            sectors=[industry, f"  {veto_industry}  "],
            signal_at=cutoff,
        )
        signal_types = (
            "funding",
            "hiring",
            "program_milestone",
            "expansion",
            "leadership",
            "other",
        )
        companies_by_signal_type = []
        for signal_type in signal_types:
            company_id = _company(conn, sectors=[industry])
            _signal(conn, company_id, signal_type, cutoff)
            companies_by_signal_type.append(company_id)
        _signal(conn, qualified, "funding", cutoff)
        _signal(conn, qualified, "hiring", cutoff + timedelta(days=1))
        _signal(conn, qualified, "program_milestone", as_of)
        _signal(conn, qualified, "expansion", as_of + timedelta(seconds=1))
        _signal(conn, qualified, "leadership", as_of + timedelta(seconds=2))
        _signal(conn, qualified, "other", as_of + timedelta(seconds=3))
        conn.commit()

    criteria = CompiledCriteria(
        industries=(industry, "Fintech"),
        company_sizes=("0-10", "11-100"),
        countries=("Germany", "Netherlands"),
        excluded_company_ids=(),
        excluded_industries=(veto_industry.lower(),),
        excluded_countries=(),
    )
    with psycopg.connect(integration_database_url) as conn:
        candidates = SqlCandidateRepository(conn).find_candidates(
            criteria, SignalWindow(cutoff, as_of)
        )
        conn.rollback()
    assert tuple(candidate.company_id for candidate in candidates) == tuple(
        sorted(
            (qualified, *companies_by_signal_type),
            key=lambda company_id: company_id.int,
        )
    )


def test_candidate_query_rejects_unknown_attributes_and_country_aliases(
    integration_database_url: str,
):
    cutoff, as_of = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 7, tzinfo=UTC)
    with psycopg.connect(integration_database_url) as conn:
        missing_attributes = [
            _company(conn, sectors=None, signal_at=cutoff),
            _company(conn, sectors=[], signal_at=cutoff),
            _company(conn, sectors=["Unspecified"], signal_at=cutoff),
            _company(conn, sectors=["SaaS"], size=None, signal_at=cutoff),
            _company(conn, sectors=["SaaS"], country=None, signal_at=cutoff),
            _company(conn, sectors=["SaaS"], country="  ", signal_at=cutoff),
            _company(conn, sectors=["SaaS"], country="USA", signal_at=cutoff),
        ]
        conn.commit()

    criteria = CompiledCriteria(
        industries=("SaaS",),
        company_sizes=("0-10",),
        countries=("United States",),
        excluded_company_ids=(),
        excluded_industries=(),
        excluded_countries=(),
    )
    with psycopg.connect(integration_database_url) as conn:
        candidates = SqlCandidateRepository(conn).find_candidates(
            criteria, SignalWindow(cutoff, as_of)
        )
        conn.rollback()
    assert not set(missing_attributes) & {
        candidate.company_id for candidate in candidates
    }


def test_insert_if_absent_preserves_existing_workflow_state_and_timestamps(
    integration_database_url: str,
):
    statuses = tuple(MatchStatus)
    user_ids = []
    expected: dict[UUID, tuple] = {}
    with psycopg.connect(integration_database_url) as conn:
        for status in statuses:
            user_id, _ = _user(conn)
            company_id = _company(conn, sectors=None)
            match_id = uuid4()
            created_at = datetime(
                2025, 1, status is MatchStatus.NEW and 1 or 2, 3, tzinfo=UTC
            )
            updated_at = created_at + timedelta(days=1)
            conn.execute(
                "INSERT INTO operational.match "
                "(id,user_id,company_id,status,notes,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,'existing note',%s,%s)",
                (match_id, user_id, company_id, status.value, created_at, updated_at),
            )
            user_ids.append((user_id, company_id))
            expected[company_id] = (
                match_id,
                status.value,
                "existing note",
                created_at,
                updated_at,
            )
        conn.commit()

    for user_id, company_id in user_ids:
        with SqlMatchmakingUnitOfWork(integration_database_url) as uow:
            assert uow.matches.insert_if_absent(user_id, company_id) is None
            uow.commit()

    with psycopg.connect(integration_database_url) as conn:
        for user_id, company_id in user_ids:
            row = conn.execute(
                "SELECT id,status,notes,created_at,updated_at FROM operational.match "
                "WHERE user_id=%s AND company_id=%s",
                (user_id, company_id),
            ).fetchone()
            assert row == expected[company_id]


def test_same_company_can_be_created_for_distinct_users(integration_database_url: str):
    with psycopg.connect(integration_database_url) as conn:
        first_user, _ = _user(conn)
        second_user, _ = _user(conn)
        company_id = _company(conn, sectors=None)
        conn.commit()

    created = []
    for user_id in (first_user, second_user):
        with SqlMatchmakingUnitOfWork(integration_database_url) as uow:
            match = uow.matches.insert_if_absent(user_id, company_id)
            assert match is not None
            assert match.user_id == user_id
            created.append(match.id)
            uow.commit()
    assert created[0] != created[1]


def test_concurrent_insert_if_absent_claims_one_match_across_connections(
    integration_database_url: str,
):
    with psycopg.connect(integration_database_url) as conn:
        user_id, _ = _user(conn)
        company_id = _company(conn, sectors=None)
        conn.commit()

    barrier = Barrier(2)

    def insert_once() -> bool:
        attempts = 0
        while True:
            attempts += 1
            try:
                with SqlMatchmakingUnitOfWork(integration_database_url) as uow:
                    barrier.wait(timeout=5) if attempts == 1 else None
                    result = uow.matches.insert_if_absent(user_id, company_id)
                    uow.commit()
                    return result is not None
            except RetryableTransactionError:
                if attempts >= 3:
                    raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(insert_once)
        second = pool.submit(insert_once)
        claims = (first.result(timeout=10), second.result(timeout=10))
    assert sorted(claims) == [False, True]

    with psycopg.connect(integration_database_url) as conn:
        count = conn.execute(
            "SELECT count(*) FROM operational.match WHERE user_id=%s AND company_id=%s",
            (user_id, company_id),
        ).fetchone()[0]
    assert count == 1
