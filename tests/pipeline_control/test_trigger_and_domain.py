from datetime import UTC, datetime
from uuid import UUID

import pytest

from huginn.pipeline_control.application.errors.trigger import TriggerRateLimitError
from huginn.pipeline_control.application.requests.trigger_invocation_request import (
    TriggerInvocationRequest,
)
from huginn.pipeline_control.application.services.trigger_invocation_service import (
    TriggerInvocationService,
)
from huginn.pipeline_control.domain.errors.invocation import (
    ActiveInvocationConflictError,
)
from huginn.pipeline_control.domain.value_objects.stage_plan import (
    SUPPORTED_STAGE_PLAN,
    StagePlan,
)

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
REQUEST_ID = UUID("00000000-0000-0000-0000-000000000002")


class _Uow:
    def __init__(self, store: dict) -> None:
        self.store = store
        self.invocations = _Invocations(store)
        self.events = _Events(store)
        self.throttle = _Throttle(store)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.store["commits"] = self.store.get("commits", 0) + 1
        if self.store.pop("fail_commit_once", False):
            raise OSError("connection lost after commit")

    def rollback(self):
        self.store["rollbacks"] = self.store.get("rollbacks", 0) + 1


class _Invocations:
    def __init__(self, store: dict) -> None:
        self.store = store

    def lock_trigger_admission(self):
        self.store["locks"] = self.store.get("locks", 0) + 1

    def get_by_request(self, account_id, request_id):
        return self.store.get("items", {}).get((account_id, request_id))

    def get(self, _id):
        return None

    def active(self):
        return self.store.get("active")

    def create(self, invocation):
        self.store.setdefault("items", {})[
            (invocation.requester_account_id, invocation.request_id)
        ] = invocation
        self.store["active"] = invocation


class _Events:
    def __init__(self, store: dict) -> None:
        self.store = store

    def append(self, event, transition_key):
        self.store.setdefault("events", []).append((event, transition_key))


class _Throttle:
    def __init__(self, store: dict) -> None:
        self.store = store

    def reserve(self, *_args):
        self.store["throttle_calls"] = self.store.get("throttle_calls", 0) + 1
        return self.store.get("retry_after")


def _service(
    store: dict, plan: StagePlan = SUPPORTED_STAGE_PLAN
) -> TriggerInvocationService:
    return TriggerInvocationService(lambda: _Uow(store), plan, clock=lambda: NOW)


def test_supported_plan_has_exact_nine_stage_graph_and_round_trips():
    assert len(SUPPORTED_STAGE_PLAN.stages) == 9
    assert StagePlan.from_json(SUPPORTED_STAGE_PLAN.to_json()) == SUPPORTED_STAGE_PLAN
    assert SUPPORTED_STAGE_PLAN.stages[6].dependencies == ("silver.signal_resolution",)


def test_same_request_returns_existing_receipt_without_counting_throttle_again():
    store: dict = {}
    request = TriggerInvocationRequest(ACCOUNT_ID, REQUEST_ID)
    first = _service(store).execute(request)
    second = _service(store).execute(request)

    assert first.created is True
    assert second.created is False
    assert second.id == first.id
    assert store["throttle_calls"] == 1
    assert len(store["events"]) == 1
    assert store["locks"] == 2


def test_distinct_request_conflict_exposes_only_active_invocation_id():
    store: dict = {}
    active = _service(store).execute(TriggerInvocationRequest(ACCOUNT_ID, REQUEST_ID))
    with pytest.raises(ActiveInvocationConflictError) as caught:
        _service(store).execute(
            TriggerInvocationRequest(
                ACCOUNT_ID, UUID("00000000-0000-0000-0000-000000000003")
            )
        )
    assert caught.value.active_invocation_id == str(active.id)
    assert len(store["events"]) == 1


def test_throttled_distinct_request_does_not_create_invocation_or_event():
    store = {"retry_after": 37}
    with pytest.raises(TriggerRateLimitError) as caught:
        _service(store).execute(TriggerInvocationRequest(ACCOUNT_ID, REQUEST_ID))
    assert caught.value.retry_after_seconds == 37
    assert store.get("items", {}) == {}
    assert store.get("events", []) == []


def test_unknown_commit_is_resolved_by_request_identity_readback():
    store = {"fail_commit_once": True}
    response = _service(store).execute(TriggerInvocationRequest(ACCOUNT_ID, REQUEST_ID))

    assert response.created is False
    assert len(store["items"]) == 1
    assert len(store["events"]) == 1
