import psycopg
import pytest

from huginn.matchmaking.persistence.errors.database import (
    CommitOutcomeUnknownError,
    DatabaseOperationError,
    DatabaseUnavailableError,
    RetryableTransactionError,
)
from huginn.matchmaking.persistence.unit_of_work.sql import (
    SqlMatchmakingUnitOfWork,
    check_readiness,
)


class Connection:
    def __init__(
        self, commit_failure=None, rollback_failure=False, close_failure=False
    ):
        self.commit_failure = commit_failure
        self.rollback_failure = rollback_failure
        self.close_failure = close_failure
        self.rollbacks = self.closes = 0

    def commit(self):
        if self.commit_failure:
            raise self.commit_failure

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_failure:
            raise psycopg.OperationalError("unsafe secret")

    def close(self):
        self.closes += 1
        if self.close_failure:
            raise psycopg.OperationalError("unsafe secret")


def test_uow_cleanup_keeps_original_failure_and_acknowledged_success(monkeypatch):
    connection = Connection(rollback_failure=True, close_failure=True)
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kw: connection)
    with (
        pytest.raises(ValueError, match="original"),
        SqlMatchmakingUnitOfWork("unused") as uow,
    ):
        assert uow.configuration._connection is connection
        assert uow.candidates._connection is connection
        assert uow.matches._connection is connection
        raise ValueError("original")
    assert connection.rollbacks == connection.closes == 1
    connection.rollbacks = 0
    with SqlMatchmakingUnitOfWork("unused") as uow:
        uow.commit()
    assert connection.rollbacks == 0


@pytest.mark.parametrize(
    "error, expected",
    (
        (psycopg.errors.SerializationFailure("raw"), RetryableTransactionError),
        (psycopg.errors.DeadlockDetected("raw"), RetryableTransactionError),
        (psycopg.errors.UniqueViolation("raw"), DatabaseOperationError),
        (psycopg.OperationalError("raw"), CommitOutcomeUnknownError),
    ),
)
def test_commit_classification_and_no_uncertain_rollback(monkeypatch, error, expected):
    connection = Connection(commit_failure=error)
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kw: connection)
    with pytest.raises(expected), SqlMatchmakingUnitOfWork("unused") as uow:
        uow.commit()
    assert connection.rollbacks == (0 if expected is CommitOutcomeUnknownError else 1)


def test_connection_establishment_unavailable(monkeypatch):
    def fail(*args, **kwargs):
        raise psycopg.OperationalError("secret")

    monkeypatch.setattr(psycopg, "connect", fail)
    with pytest.raises(DatabaseUnavailableError), SqlMatchmakingUnitOfWork("unused"):
        pass


def test_live_readiness_and_repeatable_read_snapshot(integration_database_url):
    from tests.matchmaking.test_schema_migrations import _insert_user_and_company

    check_readiness(integration_database_url)
    with psycopg.connect(integration_database_url) as seed:
        user, company = _insert_user_and_company(seed)
    with SqlMatchmakingUnitOfWork(integration_database_url) as uow:
        assert uow.configuration.user_availability(user) == "active"
        with psycopg.connect(integration_database_url) as editor:
            editor.execute(
                "UPDATE operational.accounts SET status='disabled' WHERE id=(SELECT account_id FROM operational.users WHERE id=%s)",
                (user,),
            )
        assert uow.configuration.user_availability(user) == "active"
        assert (
            uow._connection.execute("SHOW transaction_isolation").fetchone()[0]
            == "repeatable read"
        )
    with SqlMatchmakingUnitOfWork(integration_database_url) as uow:
        assert uow.configuration.user_availability(user) == "disabled"


def test_live_partial_insertion_is_rolled_back(integration_database_url):
    from uuid import uuid4

    from tests.matchmaking.test_schema_migrations import _insert_user_and_company

    with psycopg.connect(integration_database_url) as seed:
        user, company = _insert_user_and_company(seed)
    with (
        pytest.raises(DatabaseOperationError),
        SqlMatchmakingUnitOfWork(integration_database_url) as uow,
    ):
        assert uow.matches.insert_if_absent(user, company)
        uow.matches.insert_if_absent(user, uuid4())
    with psycopg.connect(integration_database_url) as check:
        assert (
            check.execute(
                "SELECT count(*) FROM operational.match WHERE user_id=%s", (user,)
            ).fetchone()[0]
            == 0
        )


def test_enter_isolation_failure_is_translated_and_cleaned(monkeypatch):
    class BrokenIsolation(Connection):
        @property
        def isolation_level(self):
            return None

        @isolation_level.setter
        def isolation_level(self, value):
            raise psycopg.OperationalError("secret driver message")

    connection = BrokenIsolation()
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kw: connection)
    with pytest.raises(DatabaseOperationError), SqlMatchmakingUnitOfWork("unused"):
        raise AssertionError("unreachable")
    assert connection.rollbacks == connection.closes == 1


def test_live_strategy_and_icp_edits_apply_next_snapshot(integration_database_url):
    from uuid import uuid4

    from tests.matchmaking.test_sql_repositories import _user

    with psycopg.connect(integration_database_url) as seed:
        user, _ = _user(seed)
        offering, icp, strategy = uuid4(), uuid4(), uuid4()
        seed.execute(
            "INSERT INTO operational.service_offerings(id,user_id,name,description) VALUES(%s,%s,'Offer','Description')",
            (offering, user),
        )
        seed.execute(
            "INSERT INTO operational.ideal_client_profiles(id,user_id,name,industries) VALUES(%s,%s,'ICP','[{\"name\":\"SaaS\"}]')",
            (icp, user),
        )
        seed.execute(
            "INSERT INTO operational.client_discovery_strategies(id,user_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES(%s,%s,'Strategy',%s,%s,TRUE)",
            (strategy, user, offering, icp),
        )
    with SqlMatchmakingUnitOfWork(integration_database_url) as uow:
        before = uow.configuration.list_active_strategies(user)
        with psycopg.connect(integration_database_url) as editor:
            editor.execute(
                "UPDATE operational.ideal_client_profiles SET industries='[]' WHERE id=%s",
                (icp,),
            )
            editor.execute(
                "UPDATE operational.client_discovery_strategies SET is_active=FALSE WHERE id=%s",
                (strategy,),
            )
        assert uow.configuration.list_active_strategies(user) == before
    with SqlMatchmakingUnitOfWork(integration_database_url) as uow:
        assert uow.configuration.list_active_strategies(user) == ()
