from datetime import timedelta

import pytest

from huginn.management.application.requests.change_prospect_stage_request import (
    ChangeProspectStageRequest,
)
from huginn.management.application.services.change_prospect_stage_service import (
    ChangeProspectStageService,
)
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_adjacent_stage_transition_records_late_occurrence_and_replays():
    store = ProspectingPursuitStore()
    service = ChangeProspectStageService(lambda: store.uow(), clock=lambda: NOW)
    request = ChangeProspectStageRequest(
        store.prospect.id,
        store.prospect.version,
        ProspectStage("contacted"),
        NOW - timedelta(days=2),
        "contact-late",
    )

    result = service.execute(store.principal, request)
    assert service.execute(store.principal, request) == result
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

    later = service.execute(
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
    assert service.execute(store.principal, request) == result
    assert store.prospect == later.prospect
    assert len(store.activities) == 2
    with pytest.raises(ConflictError):
        service.execute(
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
    service = ChangeProspectStageService(lambda: store.uow(), clock=lambda: NOW)
    no_reason = ChangeProspectStageRequest(
        store.prospect.id,
        store.prospect.version,
        ProspectStage("in_conversation"),
        NOW,
        "back-no-reason",
    )
    with pytest.raises(ValidationDomainError):
        service.execute(store.principal, no_reason)

    skipped = ChangeProspectStageRequest(
        store.prospect.id,
        store.prospect.version,
        ProspectStage("saved"),
        NOW,
        "skip-back",
        "review",
    )
    with pytest.raises(ValidationDomainError):
        service.execute(store.principal, skipped)
    assert store.prospect.stage == ProspectStage("proposal_sent")
    assert store.activities == []


def test_proposal_sent_is_an_explicit_transition_activity():
    store = ProspectingPursuitStore(stage="in_conversation")
    service = ChangeProspectStageService(lambda: store.uow(), clock=lambda: NOW)
    result = service.execute(
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
    service = ChangeProspectStageService(lambda: store.uow(), clock=lambda: NOW)
    result = service.execute(
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
