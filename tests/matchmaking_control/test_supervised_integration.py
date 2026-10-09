"""Real matcher, durable journal, and shared supervised CLI on disposable PG16."""

import json
import sys
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.matchmaking.application.requests.batch_matchmaking_request import (
    BatchMatchmakingRequest,
)
from huginn.matchmaking.config import MatchmakingConfig
from huginn.matchmaking.presentation.cli import _execute_guarded
from huginn.matchmaking_control.application.requests.trigger_run_request import (
    TriggerRunRequest,
)
from huginn.matchmaking_control.bootstrap import create_matchmaking_control_services
from huginn.matchmaking_control.domain.value_objects.requester import Requester
from huginn.matchmaking_control.persistence.database.unit_of_work import (
    PostgresMatchmakingControlUnitOfWork,
)
from huginn.matchmaking_control.presentation.cli.worker import run_once
from huginn.pipeline_control.application.errors.execution import (
    ExecutionUnavailableError,
)
from huginn.pipeline_control.infrastructure.postgres_execution_guard import (
    PostgresExecutionGuard,
)
from huginn.pipeline_control.infrastructure.process_supervisor import (
    ProcessExecutorSupervisor,
    new_execution_owner,
)
from tests.matchmaking.test_sql_repositories import _company, _scratch_database, _user


def test_managed_existing_matcher_and_standalone_cli_share_guard_and_preserve_matches(
    integration_database_url, monkeypatch
):
    with _scratch_database(integration_database_url) as database_url:
        monkeypatch.setenv("HUGINN_MATCHMAKING_DATABASE_URL", database_url)
        cutoff, as_of = (
            datetime(2026, 9, 1, tzinfo=UTC),
            datetime(2026, 10, 1, tzinfo=UTC),
        )
        with psycopg.connect(database_url) as connection:
            user, account = _user(connection)
            company = _company(
                connection,
                sectors=["SaaS"],
                signal_at=datetime(2026, 9, 15, tzinfo=UTC),
            )
            offering, icp, strategy = uuid4(), uuid4(), uuid4()
            connection.execute(
                "INSERT INTO operational.service_offerings(id,user_id,name,description) VALUES(%s,%s,'Offer','Description')",
                (offering, user),
            )
            connection.execute(
                "INSERT INTO operational.ideal_client_profiles(id,user_id,name,industries,company_sizes,geographies,exclusions) VALUES(%s,%s,'Profile',%s::jsonb,%s::jsonb,%s::jsonb,'[]')",
                (
                    icp,
                    user,
                    json.dumps([{"name": "SaaS"}]),
                    json.dumps([{"band": "0-10"}]),
                    json.dumps([{"kind": "country", "value": "Germany"}]),
                ),
            )
            connection.execute(
                "INSERT INTO operational.client_discovery_strategies(id,user_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES(%s,%s,'Strategy',%s,%s,TRUE)",
                (strategy, user, offering, icp),
            )
        factory = ManagementConnectionFactory(database_url, statement_timeout_ms=2000)
        services = create_matchmaking_control_services(database_url)
        receipt = services.trigger.execute(
            TriggerRunRequest(Requester(account), uuid4(), "user", cutoff, as_of, user)
        )
        collecting = PostgresExecutionGuard(factory)
        collection_owner = new_execution_owner(None)
        assert collecting.acquire(collection_owner)

        def supervise(owner):
            return ProcessExecutorSupervisor(
                command=(
                    sys.executable,
                    "-m",
                    "huginn.matchmaking_control.presentation.cli.executor",
                    "--run-id",
                    str(owner.matchmaking_run_id),
                    "--worker-id",
                    str(owner.owner_id),
                ),
                heartbeat_seconds=0.1,
            )

        try:
            waiting = run_once(
                lambda: PostgresMatchmakingControlUnitOfWork(factory),
                lambda: PostgresExecutionGuard(factory, resource_kind="matchmaking"),
                supervise,
            )
            assert waiting.status == "waiting"
            with pytest.raises(ExecutionUnavailableError, match="execution_busy"):
                _execute_guarded(
                    MatchmakingConfig(database_url),
                    BatchMatchmakingRequest((user,), cutoff, as_of),
                )
            with psycopg.connect(database_url) as connection:
                assert connection.execute(
                    "SELECT state FROM ops.matchmaking_runs WHERE id=%s", (receipt.id,)
                ).fetchone() == ("queued",)
                assert connection.execute(
                    "SELECT count(*) FROM operational.match WHERE user_id=%s", (user,)
                ).fetchone() == (0,)
        finally:
            collecting.release(collection_owner.owner_id)
        finished = run_once(
            lambda: PostgresMatchmakingControlUnitOfWork(factory),
            lambda: PostgresExecutionGuard(factory, resource_kind="matchmaking"),
            supervise,
        )
        assert finished.status == "succeeded"
        with psycopg.connect(database_url) as connection:
            target = connection.execute(
                "SELECT state,created_matches_count,existing_matches_skipped_count FROM ops.matchmaking_run_users WHERE run_id=%s",
                (receipt.id,),
            ).fetchone()
            assert target == ("succeeded", 1, 0)
            connection.execute(
                "UPDATE operational.match SET status='contacted',notes='preserve me' WHERE user_id=%s AND company_id=%s",
                (user, company),
            )
        payload, status = _execute_guarded(
            MatchmakingConfig(database_url),
            BatchMatchmakingRequest((user,), cutoff, as_of),
        )
        assert status == 0 and set(payload) == {
            "cutoff",
            "as_of",
            "responses",
            "failures",
        }
        assert payload["responses"][0]["existing_matches_skipped_count"] == 1
        assert payload["responses"][0]["created_matches"] == []
        with psycopg.connect(database_url) as connection:
            assert connection.execute(
                "SELECT status,notes FROM operational.match WHERE user_id=%s", (user,)
            ).fetchone() == ("contacted", "preserve me")
            assert connection.execute(
                "SELECT active,resource_kind,matchmaking_run_id FROM ops.pipeline_execution_guard"
            ).fetchone() == (False, "matchmaking", None)
