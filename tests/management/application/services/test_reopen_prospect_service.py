from huginn.management.application.requests.close_prospect_request import (
    CloseProspectRequest,
)
from huginn.management.application.requests.reopen_prospect_request import (
    ReopenProspectRequest,
)
from huginn.management.application.services.close_prospect_service import (
    CloseProspectService,
)
from huginn.management.application.services.reopen_prospect_service import (
    ReopenProspectService,
)
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_reopen_restores_last_active_stage_without_erasing_close_history():
    store = ProspectingPursuitStore(stage="contacted")
    closer = CloseProspectService(lambda: store.uow(), clock=lambda: NOW)
    closer.execute(
        store.principal,
        CloseProspectRequest(store.prospect.id, 1, "Budget paused", NOW, "close"),
    )
    service = ReopenProspectService(lambda: store.uow(), clock=lambda: NOW)
    result = service.execute(
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
