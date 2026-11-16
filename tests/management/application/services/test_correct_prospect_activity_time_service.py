from datetime import timedelta

import pytest

from huginn.management.application.requests.correct_prospect_activity_time_request import (
    CorrectProspectActivityTimeRequest,
)
from huginn.management.application.requests.record_proposal_draft_request import (
    RecordProposalDraftRequest,
)
from huginn.management.application.services.correct_prospect_activity_time_service import (
    CorrectProspectActivityTimeService,
)
from huginn.management.application.services.record_proposal_draft_service import (
    RecordProposalDraftService,
)
from huginn.management.domain.errors.errors import ConflictError
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_corrections_append_ordered_chain_without_mutating_original_or_prospect():
    store = ProspectingPursuitStore(stage="in_conversation")
    draft = RecordProposalDraftService(lambda: store.uow(), clock=lambda: NOW).execute(
        store.principal,
        RecordProposalDraftRequest(store.prospect.id, 1, "Pricing sent", NOW, "draft"),
    )
    service = CorrectProspectActivityTimeService(lambda: store.uow(), clock=lambda: NOW)
    first = service.execute(
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
    second = service.execute(
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
        service.execute(
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
