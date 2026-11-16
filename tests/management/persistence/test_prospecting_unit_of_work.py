from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)


class Connection:
    def __init__(self, *, fail_commit=False, fail_rollback=False):
        self.calls = []
        self.fail_commit = fail_commit
        self.fail_rollback = fail_rollback

    def cursor(self):
        connection = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, query, params):
                connection.calls.append((query, params))

        return Cursor()

    def commit(self):
        self.calls.append("commit")
        if self.fail_commit:
            raise ValueError("commit failed")

    def rollback(self):
        self.calls.append("rollback")
        if self.fail_rollback:
            raise ValueError("rollback failed")

    def close(self):
        self.calls.append("close")


def _work(connection):
    return PostgresProspectingUnitOfWork(SimpleNamespace(connect=lambda: connection))


def test_all_repositories_bind_the_identical_transaction_connection():
    connection = Connection()
    work = _work(connection)
    with work:
        for name in (
            "businesses",
            "business_recommendation_preferences",
            "recommendations",
            "assessment_revisions",
            "prospects",
            "origins",
            "activities",
            "commands",
            "offer_cycles",
            "suppression_blocks",
            "recommendation_feedback",
        ):
            assert getattr(work, name).connection is connection
        assert work.connection is connection
    assert connection.calls == ["rollback", "close"]
    assert work.connection is None


@pytest.mark.parametrize("operation", ["commit", "rollback"])
def test_explicit_transaction_finish_is_not_repeated_on_exit(operation):
    connection = Connection()
    work = _work(connection)
    with work:
        getattr(work, operation)()
        with pytest.raises(RuntimeError, match="finished"):
            work.lock_business_company(uuid4(), uuid4())
    assert connection.calls == [operation, "close"]


def test_body_error_rolls_back_and_closes_without_masking_original_error():
    connection = Connection(fail_rollback=True)
    work = _work(connection)
    with pytest.raises(RuntimeError, match="original failure"), work:
        raise RuntimeError("original failure")
    assert connection.calls == ["rollback", "close"]
    assert work.connection is None


def test_commit_error_rolls_back_once_and_closes():
    connection = Connection(fail_commit=True)
    work = _work(connection)
    with pytest.raises(ValueError, match="commit failed"), work:
        work.commit()
    assert connection.calls == ["commit", "rollback", "close"]
    assert work.connection is None


def test_binding_error_releases_an_already_opened_connection(monkeypatch):
    from huginn.management.persistence.database import (
        prospecting_unit_of_work as module,
    )

    def fail(_):
        raise RuntimeError("repository binding failed")

    monkeypatch.setattr(module, "PostgresRecommendationRepository", fail)
    connection = Connection(fail_rollback=True)
    work = _work(connection)
    with pytest.raises(RuntimeError, match="repository binding failed"):
        work.__enter__()
    assert connection.calls == ["rollback", "close"]
    assert work.connection is None


def test_pair_lock_is_transaction_scoped_and_bound_to_both_ids():
    connection = Connection()
    business_id, company_id = uuid4(), uuid4()
    work = _work(connection)
    with work:
        work.lock_business_company(business_id, company_id)
    query, params = connection.calls[0]
    assert "pg_advisory_xact_lock" in query
    assert params == (f"huginn:prospecting:{business_id}:{company_id}",)
    with pytest.raises(RuntimeError, match="not active"):
        work.lock_business_company(business_id, company_id)


def test_reentering_active_work_does_not_leak_its_connection():
    connection = Connection()
    work = _work(connection)
    with work, pytest.raises(RuntimeError, match="already active"):
        work.__enter__()
    assert connection.calls == ["rollback", "close"]


def test_read_only_work_starts_snapshot_before_repository_access_and_cannot_claim():
    connection = Connection()
    work = PostgresProspectingUnitOfWork(
        SimpleNamespace(connect=lambda: connection), read_only=True
    )
    with work:
        assert "REPEATABLE READ" in connection.calls[0][0]
        assert "READ ONLY" in connection.calls[0][0]
        assert work.recommendations.connection is connection
        with pytest.raises(RuntimeError, match="read-only"):
            work.lock_business_company(uuid4(), uuid4())
    assert connection.calls[1:] == ["rollback", "close"]
