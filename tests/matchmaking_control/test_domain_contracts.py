from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.matchmaking_control.domain.entities.matchmaking_run import MatchmakingRun
from huginn.matchmaking_control.domain.value_objects.requester import Requester
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.domain.value_objects.run_target import RunTarget
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState


def test_run_snapshot_is_immutable_and_target_states_define_settled_progress() -> None:
    now = datetime.now(UTC)
    user_id = uuid4()
    target = RunTarget(user_id=user_id, ordinal=0, state=TargetState.PENDING)
    run = MatchmakingRun(
        id=uuid4(),
        requester=Requester(account_id=uuid4()),
        request_id=uuid4(),
        canonical_request={"as_of": None},
        target_kind="user",
        cutoff=now - timedelta(days=30),
        as_of=now,
        state=RunState.QUEUED,
        requested_at=now,
        target_count=1,
        settled_target_count=0,
        targets=(target,),
    )

    assert run.unsettled_target_count == 1
    with pytest.raises(FrozenInstanceError):
        run.state = RunState.RUNNING
    assert replace(run, state=RunState.RUNNING).state is RunState.RUNNING
    assert RunTarget(
        user_id=user_id, ordinal=0, state=TargetState.NOT_EXECUTED
    ).is_settled
    assert not target.is_settled
