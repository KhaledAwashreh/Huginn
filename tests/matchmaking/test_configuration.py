import importlib
from datetime import UTC, datetime

import psycopg
import pytest

from huginn.matchmaking.application.errors.execution import ConfigurationError
from huginn.matchmaking.application.requests.batch_matchmaking_request import (
    BatchMatchmakingRequest,
)
from huginn.matchmaking.bootstrap import build_batch_service
from huginn.matchmaking.config import MatchmakingConfig
from huginn.matchmaking.persistence.errors.database import DatabaseOperationError
from huginn.matchmaking.persistence.unit_of_work.sql import check_readiness
from tests.matchmaking.test_schema_migrations import _scratch_database


@pytest.mark.parametrize("value", ("", " ", "invalid DSN", "postgresql://localhost"))
def test_missing_invalid_configuration_is_safe(value):
    with pytest.raises(ConfigurationError) as exc:
        MatchmakingConfig(value)
    assert value not in str(exc.value) if value.strip() else True


def test_inert_import_composition_and_empty_batch(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("connection opened")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    import huginn.matchmaking.bootstrap as bootstrap

    importlib.reload(bootstrap)
    service = build_batch_service(MatchmakingConfig("postgresql://localhost/huginn"))
    response = service.execute(
        BatchMatchmakingRequest((), datetime(2026, 1, 1, tzinfo=UTC))
    )
    assert response.responses == response.failures == ()


def test_readiness_refuses_missing_and_deferrable_identity_without_mutation(
    integration_database_url,
):
    with (
        _scratch_database(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(
            "ALTER TABLE operational.match DROP CONSTRAINT match_user_company_unique"
        )
        with pytest.raises(DatabaseOperationError):
            check_readiness(url)
        conn.execute(
            "ALTER TABLE operational.match ADD CONSTRAINT match_user_company_unique UNIQUE(user_id,company_id) DEFERRABLE"
        )
        with pytest.raises(DatabaseOperationError):
            check_readiness(url)
        assert conn.execute(
            "SELECT condeferrable FROM pg_constraint WHERE conrelid='operational.match'::regclass AND conname='match_user_company_unique'"
        ).fetchone()[0]


def test_readiness_server_rejection_maps_to_safe_batch_failure(monkeypatch):
    class BrokenProbe:
        def execute(self, query):
            raise psycopg.errors.DeadlockDetected("unsafe server details")

        def close(self):
            pass

    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: BrokenProbe())
    from uuid import uuid4

    ids = tuple(sorted((uuid4(), uuid4())))
    batch = build_batch_service(MatchmakingConfig("postgresql://localhost/huginn"))
    response = batch.execute(
        BatchMatchmakingRequest(ids, datetime(2026, 1, 1, tzinfo=UTC))
    )
    assert (
        response.responses == () and tuple(f.user_id for f in response.failures) == ids
    )
    assert all(f.reason == "database_failure" for f in response.failures)
