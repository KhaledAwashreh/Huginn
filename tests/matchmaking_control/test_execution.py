from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.matchmaking_control.application.errors.execution import (
    ResultTrackingUncertainError,
)
from huginn.matchmaking_control.application.read_models.user_result import UserResult
from huginn.matchmaking_control.application.requests.execute_run_request import (
    ExecuteRunRequest,
)
from huginn.matchmaking_control.application.services.execute_run_service import (
    ExecuteRunService,
)
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState


class Uow:
    def __init__(self, repository, fail_commit=False):
        self.runs = repository
        self.fail_commit = fail_commit

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        if self.fail_commit:
            raise OSError("journal disconnected")


class Repository:
    def __init__(self):
        self.id, self.worker, self.first, self.second = (
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        self.run = SimpleNamespace(
            id=self.id,
            worker_id=str(self.worker),
            state=RunState.RUNNING,
            cutoff=datetime(2026, 9, 1, tzinfo=UTC),
            as_of=datetime(2026, 10, 1, tzinfo=UTC),
        )
        self.targets = tuple(
            UserResult(self.id, user, index, TargetState.PENDING)
            for index, user in enumerate((self.first, self.second))
        )
        self.calls = []
        self.recorded = None

    def get_run_snapshot(self, *args):
        return self.run

    def pending_targets(self, *args):
        return self.targets

    def start_target(self, run, user, worker, now):
        self.calls.append(("start", user))
        return True

    def acknowledge_target(self, result, skipped, worker, now):
        self.calls.append(("ack", result.user_id))
        self.recorded = result
        return True

    def get_target(self, *args):
        return self.recorded


class Executor:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, user, cutoff, as_of):
        assert self.repository.calls[-1] == ("start", user)
        self.repository.calls.append(("evaluate", user))
        return UserResult(
            self.repository.id,
            user,
            0,
            TargetState.SUCCEEDED,
            strategies_evaluated=0,
            strategies_skipped=0,
            unique_candidates_count=0,
            created_matches_count=0,
            existing_matches_skipped_count=0,
        ), ()


def test_serial_journal_receipt_loss_reads_acknowledged_state_without_replay():
    repository = Repository()
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return Uow(repository, fail_commit=calls == 3)

    service = ExecuteRunService(factory, Executor(repository))
    assert (
        service.execute(ExecuteRunRequest(repository.id, repository.worker)).status
        == "evaluated"
    )
    assert repository.calls == [
        (kind, user)
        for user in (repository.first, repository.second)
        for kind in ("start", "evaluate", "ack")
    ]


def test_missing_result_acknowledgement_stops_next_target_without_replay():
    repository = Repository()

    def fail(result, *args):
        repository.calls.append(("ack", result.user_id))
        raise OSError("result journal unavailable")

    repository.acknowledge_target = fail
    with pytest.raises(ResultTrackingUncertainError):
        ExecuteRunService(lambda: Uow(repository), Executor(repository)).execute(
            ExecuteRunRequest(repository.id, repository.worker)
        )
    assert repository.calls == [
        (kind, repository.first) for kind in ("start", "evaluate", "ack")
    ]


def test_worker_busy_does_not_mark_queued_run_running():
    from huginn.matchmaking_control.presentation.cli.worker import run_once

    repository = Repository()
    repository.claim_next_run = lambda *args: repository.run
    repository.start_run = lambda *args: pytest.fail("busy guard must not start run")

    class Guard:
        def acquire(self, owner):
            return False

        def close(self):
            pass

    assert (
        run_once(
            lambda: Uow(repository),
            lambda: Guard(),
            lambda owner: pytest.fail("busy guard must not supervise"),
        ).status
        == "waiting"
    )
