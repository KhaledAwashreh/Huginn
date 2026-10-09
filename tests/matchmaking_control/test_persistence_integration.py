"""Durable matchmaking admission and journal behavior on disposable PG16."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.matchmaking_control.application.read_models.skipped_strategy_result import (
    SkippedStrategyResult,
)
from huginn.matchmaking_control.application.read_models.user_result import UserResult
from huginn.matchmaking_control.application.requests.list_target_users_request import (
    ListTargetUsersRequest,
)
from huginn.matchmaking_control.application.requests.trigger_run_request import (
    TriggerRunRequest,
)
from huginn.matchmaking_control.application.services.list_target_users_service import (
    ListTargetUsersService,
)
from huginn.matchmaking_control.application.services.trigger_run_service import (
    TriggerRunService,
)
from huginn.matchmaking_control.domain.errors.run import (
    ActiveRunConflictError,
    RequestIdentityConflictError,
)
from huginn.matchmaking_control.domain.value_objects.requester import Requester
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState
from huginn.matchmaking_control.persistence.database.unit_of_work import (
    PostgresMatchmakingControlUnitOfWork,
)
from tests.ops.test_pipeline_control_schema_integration import (
    BASE_SCHEMA_FILES,
    SCHEMA_FILES,
    _apply,
    _empty_database,
)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def _insert_account(connection: psycopg.Connection, label: str) -> tuple[UUID, UUID]:
    account_id, user_id = uuid4(), uuid4()
    connection.execute(
        "INSERT INTO operational.accounts(id,username,password_hash,status) VALUES (%s,%s,'test-hash','active')",
        (account_id, f"{label}-{account_id.hex[:10]}"),
    )
    connection.execute(
        "INSERT INTO operational.users(id,account_id,first_name,last_name,email,phone_number,country_of_residence) VALUES (%s,%s,%s,'Tester',%s,'000','US')",
        (user_id, account_id, label, f"{user_id.hex}@example.test"),
    )
    return account_id, user_id


def _insert_eligible_user(
    connection: psycopg.Connection, label: str
) -> tuple[UUID, UUID]:
    account_id, user_id = _insert_account(connection, label)
    offering_id, profile_id, strategy_id = uuid4(), uuid4(), uuid4()
    connection.execute(
        "INSERT INTO operational.service_offerings(id,user_id,name,description) VALUES (%s,%s,'Offering','Test offering')",
        (offering_id, user_id),
    )
    connection.execute(
        "INSERT INTO operational.ideal_client_profiles(id,user_id,name) VALUES (%s,%s,'Profile')",
        (profile_id, user_id),
    )
    connection.execute(
        "INSERT INTO operational.client_discovery_strategies(id,user_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,%s,'Strategy',%s,%s,true)",
        (strategy_id, user_id, offering_id, profile_id),
    )
    return account_id, user_id


def _services(database_url: str, now: datetime):
    factory = ManagementConnectionFactory(database_url)

    def uow_factory() -> PostgresMatchmakingControlUnitOfWork:
        return PostgresMatchmakingControlUnitOfWork(factory)

    trigger = TriggerRunService(uow_factory, _Clock(now))
    return uow_factory, trigger


def _apply_full_schema(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        _apply(connection, SCHEMA_FILES)


def test_all_eligible_admission_snapshots_over_one_hundred_and_replays_by_identity(
    integration_database_url: str,
) -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    with _empty_database(integration_database_url) as database_url:
        _apply_full_schema(database_url)
        with psycopg.connect(database_url, autocommit=True) as connection:
            requester_account_id, _ = _insert_account(connection, "admin")
            original_users = [
                _insert_eligible_user(connection, f"target-{index}")[1]
                for index in range(101)
            ]
        uow_factory, trigger = _services(database_url, now)
        request = TriggerRunRequest(
            requester=Requester(requester_account_id),
            request_id=uuid4(),
            target_kind="all_eligible",
            cutoff=now - timedelta(days=30),
        )

        receipt = trigger.execute(request)
        with psycopg.connect(database_url, autocommit=True) as connection:
            _insert_eligible_user(connection, "added-after-admission")
        replay = trigger.execute(request)

        assert receipt.id == replay.id
        assert receipt.target_count == replay.target_count == 101
        with pytest.raises(RequestIdentityConflictError):
            trigger.execute(replace(request, cutoff=now - timedelta(days=7)))
        with pytest.raises(ActiveRunConflictError):
            trigger.execute(replace(request, request_id=uuid4()))

        with uow_factory() as uow:
            snapshot = uow.runs.get_run_snapshot(receipt.id)
            assert snapshot is not None
            assert tuple(target.user_id for target in snapshot.targets) == tuple(
                sorted(original_users)
            )
            first = uow.runs.list_user_results(receipt.id, 100, 0)
            second = uow.runs.list_user_results(receipt.id, 100, 100)
            assert first is not None and first.has_more and len(first.items) == 100
            assert second is not None and not second.has_more and len(second.items) == 1
        user_service = ListTargetUsersService(uow_factory)
        first_users = user_service.execute(ListTargetUsersRequest(limit=100))
        assert first_users.total_eligible_count == 102
        assert first_users.page.has_more and len(first_users.page.items) == 100
        with psycopg.connect(database_url) as connection:
            assert connection.execute(
                "SELECT count(*) FROM ops.matchmaking_trigger_throttle WHERE requester_account_id=%s",
                (requester_account_id,),
            ).fetchone() == (2,)


def test_journal_acknowledges_skipped_results_and_reconcile_never_replays(
    integration_database_url: str,
) -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    with _empty_database(integration_database_url) as database_url:
        _apply_full_schema(database_url)
        with psycopg.connect(database_url, autocommit=True) as connection:
            requester_account_id, _ = _insert_account(connection, "admin")
            target_one_account, target_one = _insert_eligible_user(connection, "one")
            target_two_account, target_two = _insert_eligible_user(connection, "two")
        uow_factory, trigger = _services(database_url, now)
        first_request = TriggerRunRequest(
            requester=Requester(requester_account_id),
            request_id=uuid4(),
            target_kind="all_eligible",
            cutoff=now - timedelta(days=30),
        )
        first_run = trigger.execute(first_request)
        assert first_run.target_count == 2
        worker_id = uuid4()
        started_at = now + timedelta(seconds=1)
        finished_at = started_at + timedelta(seconds=2)
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(
                "UPDATE operational.accounts SET status='disabled' WHERE id=%s",
                (target_two_account,),
            )
        with uow_factory() as uow:
            assert uow.runs.start_run(first_run.id, worker_id, started_at)
            uow.commit()
        with uow_factory() as uow:
            snapshot = uow.runs.get_run_snapshot(first_run.id)
            assert snapshot is not None
            ordinals = {target.user_id: target.ordinal for target in snapshot.targets}
            assert uow.runs.start_target(
                first_run.id, target_one, worker_id, started_at
            )
            acknowledged = uow.runs.acknowledge_target(
                UserResult(
                    run_id=first_run.id,
                    user_id=target_one,
                    ordinal=ordinals[target_one],
                    state=TargetState.SUCCEEDED,
                    started_at=started_at,
                    finished_at=finished_at,
                    strategies_evaluated=2,
                    strategies_skipped=1,
                    unique_candidates_count=3,
                    created_matches_count=2,
                    existing_matches_skipped_count=1,
                ),
                (SkippedStrategyResult(uuid4(), "incomplete_icp"),),
                worker_id,
                finished_at,
            )
            assert acknowledged
            # A settled owner's result stays acknowledged while a sibling
            # remains active under a stale run heartbeat.
            owner_projection = uow.runs.latest_owner_result(target_one)
            active_projection = uow.runs.latest_owner_result(target_two)
            assert owner_projection is not None
            assert owner_projection["tracking_stale"] is False
            assert owner_projection["created_matches_count"] == 2
            assert active_projection is not None
            assert active_projection["tracking_stale"] is True
            assert uow.runs.start_target(
                first_run.id, target_two, worker_id, started_at
            )
            assert uow.runs.acknowledge_target(
                UserResult(
                    run_id=first_run.id,
                    user_id=target_two,
                    ordinal=ordinals[target_two],
                    state=TargetState.DISABLED_USER,
                    started_at=started_at,
                    finished_at=finished_at,
                    safe_reason="disabled_user",
                ),
                (),
                worker_id,
                finished_at,
            )
            assert uow.runs.finish_run(first_run.id, worker_id, finished_at)
            uow.commit()
        with uow_factory() as uow:
            detail = uow.runs.get_run(first_run.id)
            result = uow.runs.get_target(first_run.id, target_one)
            skipped = uow.runs.list_skipped_strategies(first_run.id, target_one, 10, 0)
            owner_result = uow.runs.latest_owner_result(target_one)
            skipped_owner_result = uow.runs.latest_owner_result(target_two)
            assert detail is not None and detail.state is RunState.SUCCEEDED
            assert detail.succeeded_count == 1 and detail.skipped_count == 1
            assert detail.created_matches_count == 2 and detail.counts_complete
            assert detail.settled_target_count == 2
            assert result is not None and result.strategies_skipped == 1
            assert skipped is not None and len(skipped.items) == 1
            assert owner_result is not None
            assert set(owner_result) == {
                "state",
                "requested_at",
                "started_at",
                "finished_at",
                "cutoff",
                "as_of",
                "tracking_stale",
                "strategies_evaluated",
                "strategies_skipped",
                "created_matches_count",
                "existing_matches_skipped_count",
            }
            assert owner_result["state"] is TargetState.SUCCEEDED
            assert owner_result["created_matches_count"] == 2
            assert skipped_owner_result is not None
            assert skipped_owner_result["state"] is TargetState.DISABLED_USER
            assert skipped_owner_result["created_matches_count"] is None
            assert uow.runs.latest_owner_result(uuid4()) is None

        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(
                "UPDATE operational.accounts SET status='active' WHERE id=%s",
                (target_two_account,),
            )
        second_request = replace(
            first_request, request_id=uuid4(), target_kind="all_eligible", user_id=None
        )
        second_run = trigger.execute(second_request)
        assert second_run.target_count == 2
        with uow_factory() as uow:
            assert uow.runs.start_run(second_run.id, worker_id, started_at)
            uow.commit()
        with uow_factory() as uow:
            pending = uow.runs.pending_targets(second_run.id, worker_id)
            assert len(pending) == 2
            running_user_id = pending[0].user_id
            assert uow.runs.start_target(
                second_run.id, running_user_id, worker_id, started_at
            )
            current = uow.runs.get_run(second_run.id)
            assert current is not None and current.current_user_id == running_user_id
            assert uow.runs.reconcile_run(second_run.id, worker_id, finished_at)
            uow.commit()
        with uow_factory() as uow:
            detail = uow.runs.get_run(second_run.id)
            results = uow.runs.list_user_results(second_run.id, 10, 0)
            assert detail is not None and detail.state is RunState.INTERRUPTED
            assert detail.uncertain_count == 1 and detail.not_executed_count == 1
            assert not detail.counts_complete
            assert detail.created_matches_count is None
            assert results is not None
            assert {item.state for item in results.items} == {
                TargetState.COMMIT_OUTCOME_UNKNOWN,
                TargetState.NOT_EXECUTED,
            }

        queued_run = trigger.execute(replace(first_request, request_id=uuid4()))
        with uow_factory() as uow:
            assert uow.runs.reconcile_run(queued_run.id, worker_id, finished_at)
            uow.commit()
        with uow_factory() as uow:
            detail = uow.runs.get_run(queued_run.id)
            results = uow.runs.list_user_results(queued_run.id, 10, 0)
            assert detail is not None and detail.state is RunState.INTERRUPTED
            assert detail.not_executed_count == 2 and detail.uncertain_count == 0
            assert results is not None and all(
                result.state is TargetState.NOT_EXECUTED for result in results.items
            )


def test_additive_guard_migration_preserves_pipeline_owner_and_allows_standalone_matcher(
    integration_database_url: str,
) -> None:
    requester_id, invocation_id, owner_id, execution_id = (uuid4() for _ in range(4))
    with (
        _empty_database(integration_database_url) as database_url,
        psycopg.connect(database_url, autocommit=True) as connection,
    ):
        _apply(connection, BASE_SCHEMA_FILES)
        _apply(
            connection,
            ("operational-account-role.sql", "ops-pipeline-control.sql"),
        )
        connection.execute(
            "INSERT INTO operational.accounts(id,username,password_hash,status) VALUES (%s,'pipeline-admin','test-hash','active')",
            (requester_id,),
        )
        connection.execute(
            "INSERT INTO ops.pipeline_invocations(id,requester_account_id,request_id,state,requested_at,plan) VALUES (%s,%s,%s,'running',now(),'{}')",
            (invocation_id, requester_id, uuid4()),
        )
        connection.execute(
            "UPDATE ops.pipeline_execution_guard SET owner_id=%s,execution_id=%s,invocation_id=%s,host='test',supervisor_pid=10,supervisor_started_at='start',executor_pid=11,executor_started_at='child',acquired_at=now(),active=true WHERE singleton=1",
            (owner_id, execution_id, invocation_id),
        )
        _apply(connection, ("ops-matchmaking-control.sql",))
        preserved = connection.execute(
            "SELECT active,owner_id,execution_id,invocation_id,resource_kind,matchmaking_run_id FROM ops.pipeline_execution_guard WHERE singleton=1"
        ).fetchone()
        assert preserved == (
            True,
            owner_id,
            execution_id,
            invocation_id,
            "pipeline",
            None,
        )
        _apply(connection, ("ops-matchmaking-control.sql",))
        connection.execute(
            "UPDATE ops.pipeline_execution_guard SET resource_kind='matchmaking',invocation_id=NULL,matchmaking_run_id=NULL WHERE singleton=1"
        )
        _apply(connection, ("ops-matchmaking-control.sql",))
        assert connection.execute(
            "SELECT active,owner_id,execution_id,resource_kind,matchmaking_run_id FROM ops.pipeline_execution_guard WHERE singleton=1"
        ).fetchone() == (True, owner_id, execution_id, "matchmaking", None)
