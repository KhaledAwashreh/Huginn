from huginn.management.application.requests.record_proposal_draft_request import (
    RecordProposalDraftRequest,
)
from huginn.management.application.services.record_proposal_draft_service import (
    RecordProposalDraftService,
)
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_proposal_draft_is_activity_only_and_never_advances_stage():
    store = ProspectingPursuitStore(stage="in_conversation")
    result = RecordProposalDraftService(lambda: store.uow(), clock=lambda: NOW).execute(
        store.principal,
        RecordProposalDraftRequest(
            store.prospect.id, 1, "Drafted a scope for review", NOW, "draft"
        ),
    )
    assert result.prospect.stage == ProspectStage("in_conversation")
    assert result.prospect.version == 1
    assert result.activity.kind.value == "proposal_drafted"
    assert result.activity.payload.value == {"summary": "Drafted a scope for review"}
