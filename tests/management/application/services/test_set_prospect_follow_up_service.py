from datetime import timedelta

from huginn.management.application.requests.set_prospect_follow_up_request import (
    SetProspectFollowUpRequest,
)
from huginn.management.application.services.set_prospect_follow_up_service import (
    SetProspectFollowUpService,
)
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_setting_due_follow_up_changes_only_date_and_records_occurrence():
    store = ProspectingPursuitStore()
    service = SetProspectFollowUpService(lambda: store.uow(), clock=lambda: NOW)
    follow_up_at = NOW - timedelta(days=1)
    result = service.execute(
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
