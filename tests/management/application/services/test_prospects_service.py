from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from huginn.management.application.services.prospects import ProspectService
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_adjacent_stage_transition_records_late_occurrence_and_replays():
    store = ProspectingPursuitStore()
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    request = {
        "prospect_id": store.prospect.id,
        "expected_version": store.prospect.version,
        "target_stage": ProspectStage("contacted"),
        "occurred_at": NOW - timedelta(days=2),
        "request_key": "contact-late",
    }

    result = service.change_stage(store.principal, **request)
    assert service.change_stage(store.principal, **request) == result
    assert result.prospect.stage == ProspectStage("contacted")
    assert result.prospect.version == store.prospect.version == 2
    assert result.activity.kind.value == "stage_changed"
    assert result.activity.occurred_at == NOW - timedelta(days=2)
    assert result.activity.recorded_at == NOW
    assert result.activity.payload.value == {
        "prior_stage": "saved",
        "new_stage": "contacted",
        "reason": None,
    }
    assert len(store.activities) == len(store.receipts) == 1

    later = service.change_stage(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=store.prospect.version,
        target_stage=ProspectStage("in_conversation"),
        occurred_at=NOW,
        request_key="stage-later",
    )
    assert later.prospect.version == 3
    replay = service.change_stage(store.principal, **request)
    assert replay.prospect == later.prospect
    assert replay.activity == result.activity
    assert store.prospect == later.prospect
    assert len(store.activities) == 2
    with pytest.raises(ConflictError):
        service.change_stage(
            store.principal,
            prospect_id=request["prospect_id"],
            expected_version=request["expected_version"],
            target_stage=ProspectStage("proposal_sent"),
            occurred_at=request["occurred_at"],
            request_key=request["request_key"],
        )


def test_manual_receipt_keeps_only_activity_reference_and_original_version():
    store = ProspectingPursuitStore()
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.update_notes(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        replacement_notes="Updated",
        occurred_at=NOW,
        request_key="note",
    )
    receipt = store.receipts[(store.business.id, "note")]
    assert receipt.result_snapshot.value == {"activity_id": str(result.activity.id)}
    assert receipt.resource_id == result.prospect.id
    assert receipt.resource_version == result.prospect.version


def test_historical_manual_receipt_uses_only_original_activity_id():
    store = ProspectingPursuitStore()
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    request = {
        "prospect_id": store.prospect.id,
        "expected_version": 1,
        "replacement_notes": "Updated",
        "occurred_at": NOW,
        "request_key": "note",
    }
    original = service.update_notes(store.principal, **request)
    receipt = store.receipts[(store.business.id, "note")]
    store.receipts[(store.business.id, "note")] = replace(
        receipt,
        result_snapshot=JsonSnapshot(
            {
                "prospect": {"obsolete": "ignored"},
                "activity": {"id": str(original.activity.id)},
            }
        ),
    )
    later = service.update_notes(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=2,
        replacement_notes="Latest",
        occurred_at=NOW,
        request_key="later",
    )
    history = tuple(store.activities)
    replay = service.update_notes(store.principal, **request)
    assert replay.prospect == later.prospect
    assert replay.activity == original.activity
    assert tuple(store.activities) == history
    assert store.commits == 2


def test_manual_retry_does_not_return_an_activity_outside_owned_prospect():
    store = ProspectingPursuitStore()
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    request = {
        "prospect_id": store.prospect.id,
        "expected_version": 1,
        "replacement_notes": "Updated",
        "occurred_at": NOW,
        "request_key": "note",
    }
    result = service.update_notes(store.principal, **request)
    store.activities[0] = replace(result.activity, business_id=uuid4())
    with pytest.raises(NotFoundError, match="Activity not found"):
        service.update_notes(store.principal, **request)


def test_backward_stage_change_requires_reason_and_skips_are_rejected():
    store = ProspectingPursuitStore(stage="proposal_sent")
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    no_reason = {
        "prospect_id": store.prospect.id,
        "expected_version": store.prospect.version,
        "target_stage": ProspectStage("in_conversation"),
        "occurred_at": NOW,
        "request_key": "back-no-reason",
    }
    with pytest.raises(ValidationDomainError):
        service.change_stage(store.principal, **no_reason)

    skipped = {**no_reason, "target_stage": ProspectStage("saved")}
    skipped["request_key"] = "skip-back"
    skipped["reason"] = "review"
    with pytest.raises(ValidationDomainError):
        service.change_stage(store.principal, **skipped)
    assert store.prospect.stage == ProspectStage("proposal_sent")
    assert store.activities == []


def test_proposal_sent_is_an_explicit_transition_activity():
    store = ProspectingPursuitStore(stage="in_conversation")
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.change_stage(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=store.prospect.version,
        target_stage=ProspectStage("proposal_sent"),
        occurred_at=NOW,
        request_key="proposal-sent",
    )
    assert result.prospect.stage == ProspectStage("proposal_sent")
    assert result.activity.kind.value == "proposal_sent"


def test_backward_to_proposal_sent_is_not_a_second_send_event():
    store = ProspectingPursuitStore(stage="won_client")
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.change_stage(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=store.prospect.version,
        target_stage=ProspectStage("proposal_sent"),
        occurred_at=NOW,
        request_key="stage-back-to-proposal",
        reason="The client reopened price discussion",
    )
    assert result.activity.kind.value == "stage_changed"
    assert (
        result.activity.payload.value["reason"]
        == "The client reopened price discussion"
    )
    assert result.activity.payload.value["prior_stage"] == "won_client"
    assert result.activity.payload.value["new_stage"] == "proposal_sent"


def test_close_requires_reason_and_retains_last_active_stage():
    store = ProspectingPursuitStore(stage="in_conversation")
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    try:
        service.close(
            store.principal,
            prospect_id=store.prospect.id,
            expected_version=1,
            reason="",
            occurred_at=NOW,
            request_key="bad-close",
        )
    except ValidationDomainError:
        pass
    else:
        raise AssertionError("close without a reason must fail")
    result = service.close(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        reason="No longer pursuing",
        occurred_at=NOW,
        request_key="close",
    )
    assert result.prospect.stage == ProspectStage("closed")
    assert result.prospect.last_active_stage == ProspectStage("in_conversation")
    assert result.activity.kind.value == "closed"
    assert result.activity.payload.value["reason"] == "No longer pursuing"


def test_reopen_restores_last_active_stage_without_erasing_close_history():
    store = ProspectingPursuitStore(stage="contacted")
    closer = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    closer.close(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        reason="Budget paused",
        occurred_at=NOW,
        request_key="close",
    )
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.reopen(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=store.prospect.version,
        occurred_at=NOW,
        request_key="reopen",
    )
    assert result.prospect.last_active_stage is None
    assert result.prospect.stage == ProspectStage("contacted")
    assert [activity.kind.value for activity in store.activities] == [
        "closed",
        "reopened",
    ]
    assert store.activities[0].payload.value["reason"] == "Budget paused"


def test_notes_replace_and_clear_memo_while_preserving_prior_values_in_history():
    store = ProspectingPursuitStore()
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.update_notes(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        replacement_notes="Updated memo",
        occurred_at=NOW,
        request_key="memo-1",
    )
    assert result.prospect.notes == "Updated memo"
    assert result.prospect.version == 2
    assert result.activity.kind.value == "note_added"
    assert result.activity.payload.value == {
        "prior": "Existing memo",
        "replacement": "Updated memo",
    }

    cleared = service.update_notes(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=2,
        replacement_notes="",
        occurred_at=NOW,
        request_key="memo-clear",
    )
    assert cleared.prospect.notes == ""
    assert cleared.activity.payload.value == {
        "prior": "Updated memo",
        "replacement": "",
    }


def test_receipt_failure_rolls_back_note_version_activity_and_result():
    store = ProspectingPursuitStore()
    store.fail_receipt = True
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    with pytest.raises(ConflictError, match="Simulated receipt failure"):
        service.update_notes(
            store.principal,
            prospect_id=store.prospect.id,
            expected_version=1,
            replacement_notes="Uncommitted",
            occurred_at=NOW,
            request_key="rollback",
        )
    assert store.prospect.notes == "Existing memo"
    assert store.prospect.version == 1
    assert store.activities == []
    assert store.receipts == {}
    assert store.commits == 0


def test_notes_command_loads_once_before_lock_and_once_after_lock():
    store = ProspectingPursuitStore()
    events = []

    def factory():
        uow = store.uow()
        get_owned = uow.prospects.get_owned

        def read_owned(business_id, prospect_id):
            events.append("read")
            return get_owned(business_id, prospect_id)

        uow.prospects.get_owned = read_owned
        return uow

    store.after_lock = lambda: events.append("lock")
    service = ProspectService(factory, clock=lambda: NOW)
    result = service.update_notes(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        replacement_notes="Updated",
        occurred_at=NOW,
        request_key="read-once",
    )
    assert result.prospect.notes == "Updated"
    assert events == ["read", "lock", "read"]


def test_setting_due_follow_up_changes_only_date_and_records_occurrence():
    store = ProspectingPursuitStore()
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    follow_up_at = NOW - timedelta(days=1)
    result = service.set_follow_up(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        follow_up_at=follow_up_at,
        occurred_at=NOW - timedelta(days=2),
        request_key="follow-up",
    )
    assert result.prospect.follow_up_at == follow_up_at
    assert result.prospect.stage.value == "saved"
    assert result.activity.kind.value == "follow_up_set"
    assert result.activity.occurred_at == NOW - timedelta(days=2)
    assert result.activity.recorded_at == NOW


def test_clear_follow_up_is_explicit_and_does_not_change_stage():
    store = ProspectingPursuitStore()
    ProspectService(lambda: store.uow(), clock=lambda: NOW).set_follow_up(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        follow_up_at=NOW,
        occurred_at=NOW,
        request_key="set",
    )
    result = ProspectService(lambda: store.uow(), clock=lambda: NOW).clear_follow_up(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=2,
        occurred_at=NOW,
        request_key="clear",
    )
    assert result.prospect.follow_up_at is None
    assert result.prospect.stage.value == "saved"
    assert [activity.kind.value for activity in store.activities] == [
        "follow_up_set",
        "follow_up_cleared",
    ]


def test_proposal_draft_is_activity_only_and_never_advances_stage():
    store = ProspectingPursuitStore(stage="in_conversation")
    result = ProspectService(
        lambda: store.uow(), clock=lambda: NOW
    ).record_proposal_draft(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        summary="Drafted a scope for review",
        occurred_at=NOW,
        request_key="draft",
    )
    assert result.prospect.stage == ProspectStage("in_conversation")
    assert result.prospect.version == 1
    assert result.activity.kind.value == "proposal_drafted"
    assert result.activity.payload.value == {"summary": "Drafted a scope for review"}


def test_corrections_append_ordered_chain_without_mutating_original_or_prospect():
    store = ProspectingPursuitStore(stage="in_conversation")
    draft = ProspectService(
        lambda: store.uow(), clock=lambda: NOW
    ).record_proposal_draft(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        summary="Pricing sent",
        occurred_at=NOW,
        request_key="draft",
    )
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    first = service.correct_activity_time(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        original_activity_id=draft.activity.id,
        expected_correction_head_id=None,
        replacement_occurred_at=NOW - timedelta(days=2),
        request_key="correct-1",
    )
    second = service.correct_activity_time(
        store.principal,
        prospect_id=store.prospect.id,
        expected_version=1,
        original_activity_id=draft.activity.id,
        expected_correction_head_id=first.activity.id,
        replacement_occurred_at=NOW - timedelta(days=3),
        request_key="correct-2",
    )
    assert first.activity.payload.value["correction_sequence"] == 1
    assert second.activity.payload.value["correction_sequence"] == 2
    assert second.activity.correction_of_id == draft.activity.id
    assert draft.activity.occurred_at == NOW
    assert store.prospect.version == 1
    assert store.prospect.stage.value == "in_conversation"
    with pytest.raises(ConflictError):
        service.correct_activity_time(
            store.principal,
            prospect_id=store.prospect.id,
            expected_version=1,
            original_activity_id=draft.activity.id,
            expected_correction_head_id=first.activity.id,
            replacement_occurred_at=NOW - timedelta(days=4),
            request_key="stale-correction-head",
        )
