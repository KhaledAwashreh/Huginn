from datetime import timedelta

import pytest

from huginn.management.application.requests.change_prospect_stage_request import (
    ChangeProspectStageRequest,
)
from huginn.management.application.requests.clear_prospect_follow_up_request import (
    ClearProspectFollowUpRequest,
)
from huginn.management.application.requests.close_prospect_request import (
    CloseProspectRequest,
)
from huginn.management.application.requests.correct_prospect_activity_time_request import (
    CorrectProspectActivityTimeRequest,
)
from huginn.management.application.requests.record_proposal_draft_request import (
    RecordProposalDraftRequest,
)
from huginn.management.application.requests.reopen_prospect_request import (
    ReopenProspectRequest,
)
from huginn.management.application.requests.set_prospect_follow_up_request import (
    SetProspectFollowUpRequest,
)
from huginn.management.application.requests.update_prospect_notes_request import (
    UpdateProspectNotesRequest,
)
from huginn.management.application.services.prospects import ProspectService
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_adjacent_stage_transition_records_late_occurrence_and_replays():
    store = ProspectingPursuitStore()
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    request = ChangeProspectStageRequest(
        store.prospect.id,
        store.prospect.version,
        ProspectStage("contacted"),
        NOW - timedelta(days=2),
        "contact-late",
    )

    result = service.change_stage(store.principal, request)
    assert service.change_stage(store.principal, request) == result
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
        ChangeProspectStageRequest(
            store.prospect.id,
            store.prospect.version,
            ProspectStage("in_conversation"),
            NOW,
            "stage-later",
        ),
    )
    assert later.prospect.version == 3
    assert service.change_stage(store.principal, request) == result
    assert store.prospect == later.prospect
    assert len(store.activities) == 2
    with pytest.raises(ConflictError):
        service.change_stage(
            store.principal,
            ChangeProspectStageRequest(
                request.prospect_id,
                request.expected_version,
                ProspectStage("proposal_sent"),
                request.occurred_at,
                request.request_key,
            ),
        )


def test_backward_stage_change_requires_reason_and_skips_are_rejected():
    store = ProspectingPursuitStore(stage="proposal_sent")
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    no_reason = ChangeProspectStageRequest(
        store.prospect.id,
        store.prospect.version,
        ProspectStage("in_conversation"),
        NOW,
        "back-no-reason",
    )
    with pytest.raises(ValidationDomainError):
        service.change_stage(store.principal, no_reason)

    skipped = ChangeProspectStageRequest(
        store.prospect.id,
        store.prospect.version,
        ProspectStage("saved"),
        NOW,
        "skip-back",
        "review",
    )
    with pytest.raises(ValidationDomainError):
        service.change_stage(store.principal, skipped)
    assert store.prospect.stage == ProspectStage("proposal_sent")
    assert store.activities == []


def test_proposal_sent_is_an_explicit_transition_activity():
    store = ProspectingPursuitStore(stage="in_conversation")
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.change_stage(
        store.principal,
        ChangeProspectStageRequest(
            store.prospect.id,
            store.prospect.version,
            ProspectStage("proposal_sent"),
            NOW,
            "proposal-sent",
        ),
    )
    assert result.prospect.stage == ProspectStage("proposal_sent")
    assert result.activity.kind.value == "proposal_sent"


def test_backward_to_proposal_sent_is_not_a_second_send_event():
    store = ProspectingPursuitStore(stage="won_client")
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.change_stage(
        store.principal,
        ChangeProspectStageRequest(
            store.prospect.id,
            store.prospect.version,
            ProspectStage("proposal_sent"),
            NOW,
            "stage-back-to-proposal",
            "The client reopened price discussion",
        ),
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
            CloseProspectRequest(store.prospect.id, 1, "", NOW, "bad-close"),
        )
    except ValidationDomainError:
        pass
    else:
        raise AssertionError("close without a reason must fail")
    result = service.close(
        store.principal,
        CloseProspectRequest(store.prospect.id, 1, "No longer pursuing", NOW, "close"),
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
        CloseProspectRequest(store.prospect.id, 1, "Budget paused", NOW, "close"),
    )
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.reopen(
        store.principal,
        ReopenProspectRequest(store.prospect.id, store.prospect.version, NOW, "reopen"),
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
        UpdateProspectNotesRequest(store.prospect.id, 1, "Updated memo", NOW, "memo-1"),
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
        UpdateProspectNotesRequest(store.prospect.id, 2, "", NOW, "memo-clear"),
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
            UpdateProspectNotesRequest(
                store.prospect.id, 1, "Uncommitted", NOW, "rollback"
            ),
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
        UpdateProspectNotesRequest(store.prospect.id, 1, "Updated", NOW, "read-once"),
    )
    assert result.prospect.notes == "Updated"
    assert events == ["read", "lock", "read"]


def test_setting_due_follow_up_changes_only_date_and_records_occurrence():
    store = ProspectingPursuitStore()
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    follow_up_at = NOW - timedelta(days=1)
    result = service.set_follow_up(
        store.principal,
        SetProspectFollowUpRequest(
            store.prospect.id, 1, follow_up_at, NOW - timedelta(days=2), "follow-up"
        ),
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
        SetProspectFollowUpRequest(store.prospect.id, 1, NOW, NOW, "set"),
    )
    result = ProspectService(lambda: store.uow(), clock=lambda: NOW).clear_follow_up(
        store.principal,
        ClearProspectFollowUpRequest(store.prospect.id, 2, NOW, "clear"),
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
        RecordProposalDraftRequest(
            store.prospect.id, 1, "Drafted a scope for review", NOW, "draft"
        ),
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
        RecordProposalDraftRequest(store.prospect.id, 1, "Pricing sent", NOW, "draft"),
    )
    service = ProspectService(lambda: store.uow(), clock=lambda: NOW)
    first = service.correct_activity_time(
        store.principal,
        CorrectProspectActivityTimeRequest(
            store.prospect.id,
            1,
            draft.activity.id,
            None,
            NOW - timedelta(days=2),
            "correct-1",
        ),
    )
    second = service.correct_activity_time(
        store.principal,
        CorrectProspectActivityTimeRequest(
            store.prospect.id,
            1,
            draft.activity.id,
            first.activity.id,
            NOW - timedelta(days=3),
            "correct-2",
        ),
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
            CorrectProspectActivityTimeRequest(
                store.prospect.id,
                1,
                draft.activity.id,
                first.activity.id,
                NOW - timedelta(days=4),
                "stale-correction-head",
            ),
        )
