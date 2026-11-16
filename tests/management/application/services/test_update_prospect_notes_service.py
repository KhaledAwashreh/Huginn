import pytest

from huginn.management.application.requests.update_prospect_notes_request import (
    UpdateProspectNotesRequest,
)
from huginn.management.application.services.update_prospect_notes_service import (
    UpdateProspectNotesService,
)
from huginn.management.domain.errors.errors import ConflictError
from tests.management.application.services.prospecting_pursuit_store import (
    NOW,
    ProspectingPursuitStore,
)


def test_notes_replace_and_clear_memo_while_preserving_prior_values_in_history():
    store = ProspectingPursuitStore()
    service = UpdateProspectNotesService(lambda: store.uow(), clock=lambda: NOW)
    result = service.execute(
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

    cleared = service.execute(
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
    service = UpdateProspectNotesService(lambda: store.uow(), clock=lambda: NOW)
    with pytest.raises(ConflictError, match="Simulated receipt failure"):
        service.execute(
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
