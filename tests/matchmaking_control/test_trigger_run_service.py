from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.matchmaking_control.application.requests.trigger_run_request import (
    TriggerRunRequest,
)
from huginn.matchmaking_control.application.services.trigger_run_service import (
    TriggerRunService,
)
from huginn.matchmaking_control.domain.entities.matchmaking_run import MatchmakingRun
from huginn.matchmaking_control.domain.errors.run import (
    ActiveRunConflictError,
    TargetUserNotFoundError,
)
from huginn.matchmaking_control.domain.value_objects.requester import Requester
from huginn.matchmaking_control.domain.value_objects.run_state import RunState


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class _Runs:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    def admit_run(self, **arguments: object) -> tuple[MatchmakingRun, bool]:
        self.arguments = arguments
        return (
            MatchmakingRun(
                id=uuid4(),
                requester=arguments["requester"],  # type: ignore[arg-type]
                request_id=arguments["request_id"],  # type: ignore[arg-type]
                canonical_request=arguments["canonical_request"],  # type: ignore[arg-type]
                target_kind=arguments["target_kind"],  # type: ignore[arg-type]
                cutoff=arguments["cutoff"],  # type: ignore[arg-type]
                as_of=arguments["as_of"],  # type: ignore[arg-type]
                state=RunState.QUEUED,
                requested_at=arguments["requested_at"],  # type: ignore[arg-type]
                target_count=1,
                settled_target_count=0,
            ),
            False,
        )


class _UnitOfWork(AbstractContextManager):
    def __init__(self, runs: _Runs) -> None:
        self.runs = runs
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def commit(self) -> None:
        self.committed = True


class _ConflictRuns(_Runs):
    def admit_run(self, **arguments: object) -> tuple[MatchmakingRun, bool]:
        raise ActiveRunConflictError(str(uuid4()))


class _NotFoundRuns(_Runs):
    def admit_run(self, **arguments: object) -> tuple[MatchmakingRun, bool]:
        raise TargetUserNotFoundError("target user does not exist")


def test_trigger_preserves_omitted_as_of_for_idempotent_canonical_input() -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    runs = _Runs()
    uow = _UnitOfWork(runs)
    user_id = uuid4()
    request = TriggerRunRequest(
        requester=Requester(account_id=uuid4()),
        request_id=uuid4(),
        target_kind="user",
        user_id=user_id,
        cutoff=now - timedelta(days=30),
        as_of=None,
    )

    response = TriggerRunService(lambda: uow, _Clock(now)).execute(request)

    assert response.as_of == now
    assert uow.committed
    assert runs.arguments["canonical_request"] == {
        "target_kind": "user",
        "user_id": str(user_id),
        "cutoff": (now - timedelta(days=30)).isoformat(),
        "as_of": None,
    }


def test_trigger_rejects_future_or_reverse_window_before_repository_admission() -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    runs = _Runs()
    uow = _UnitOfWork(runs)
    base = TriggerRunRequest(
        requester=Requester(account_id=uuid4()),
        request_id=uuid4(),
        target_kind="all_eligible",
        cutoff=now - timedelta(days=1),
    )
    service = TriggerRunService(lambda: uow, _Clock(now))

    with pytest.raises(ValueError, match="future"):
        service.execute(replace(base, as_of=now + timedelta(seconds=1)))
    with pytest.raises(ValueError, match="cutoff"):
        service.execute(replace(base, cutoff=now + timedelta(days=1)))
    assert runs.arguments == {}


def test_distinct_active_conflict_commits_its_throttle_reservation() -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    uow = _UnitOfWork(_ConflictRuns())
    request = TriggerRunRequest(
        requester=Requester(account_id=uuid4()),
        request_id=uuid4(),
        target_kind="all_eligible",
        cutoff=now - timedelta(days=1),
    )

    with pytest.raises(ActiveRunConflictError):
        TriggerRunService(lambda: uow, _Clock(now)).execute(request)

    assert uow.committed


def test_distinct_invalid_target_attempt_commits_its_throttle_reservation() -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    uow = _UnitOfWork(_NotFoundRuns())
    request = TriggerRunRequest(
        requester=Requester(account_id=uuid4()),
        request_id=uuid4(),
        target_kind="user",
        user_id=uuid4(),
        cutoff=now - timedelta(days=1),
    )

    with pytest.raises(TargetUserNotFoundError):
        TriggerRunService(lambda: uow, _Clock(now)).execute(request)

    assert uow.committed
