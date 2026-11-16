from huginn.management.application.requests.close_prospect_request import (
    CloseProspectRequest,
)
from huginn.management.application.services.close_prospect_service import (
    CloseProspectService,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_close_requires_reason_and_retains_last_active_stage():
    store = ProspectingPursuitStore(stage="in_conversation")
    service = CloseProspectService(lambda: store.uow(), clock=lambda: NOW)
    try:
        service.execute(
            store.principal,
            CloseProspectRequest(store.prospect.id, 1, "", NOW, "bad-close"),
        )
    except ValidationDomainError:
        pass
    else:
        raise AssertionError("close without a reason must fail")
    result = service.execute(
        store.principal,
        CloseProspectRequest(store.prospect.id, 1, "No longer pursuing", NOW, "close"),
    )
    assert result.prospect.stage == ProspectStage("closed")
    assert result.prospect.last_active_stage == ProspectStage("in_conversation")
    assert result.activity.kind.value == "closed"
    assert result.activity.payload.value["reason"] == "No longer pursuing"
