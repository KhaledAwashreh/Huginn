from huginn.management.application.requests.clear_prospect_follow_up_request import (
    ClearProspectFollowUpRequest,
)
from huginn.management.application.requests.set_prospect_follow_up_request import (
    SetProspectFollowUpRequest,
)
from huginn.management.application.services.clear_prospect_follow_up_service import (
    ClearProspectFollowUpService,
)
from huginn.management.application.services.set_prospect_follow_up_service import (
    SetProspectFollowUpService,
)
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_clear_follow_up_is_explicit_and_does_not_change_stage():
    store = ProspectingPursuitStore()
    SetProspectFollowUpService(lambda: store.uow(), clock=lambda: NOW).execute(
        store.principal,
        SetProspectFollowUpRequest(store.prospect.id, 1, NOW, NOW, "set"),
    )
    result = ClearProspectFollowUpService(
        lambda: store.uow(), clock=lambda: NOW
    ).execute(
        store.principal,
        ClearProspectFollowUpRequest(store.prospect.id, 2, NOW, "clear"),
    )
    assert result.prospect.follow_up_at is None
    assert result.prospect.stage.value == "saved"
    assert [activity.kind.value for activity in store.activities] == [
        "follow_up_set",
        "follow_up_cleared",
    ]
