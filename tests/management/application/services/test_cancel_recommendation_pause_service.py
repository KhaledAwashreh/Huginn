from datetime import timedelta
from uuid import uuid4

import pytest

from huginn.management.application.requests.cancel_recommendation_pause_request import (
    CancelRecommendationPauseRequest,
)
from huginn.management.application.services.cancel_recommendation_pause_service import (
    CancelRecommendationPauseService,
)
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from tests.management.application.services.prospecting_command_store import (
    NOW,
    ProspectingCommandStore,
    pending_offer,
)


def service(store):
    return CancelRecommendationPauseService(
        store.uow, clock=lambda: NOW + timedelta(minutes=5)
    )


def request(block, *, key="cancel-pause", version=None):
    return CancelRecommendationPauseRequest(
        suppression_block_id=block.id,
        expected_version=block.version if version is None else version,
        request_key=key,
    )


def test_cancel_clears_only_the_selected_pause_and_discloses_other_blocks():
    store = ProspectingCommandStore()
    pause = store.block("pause", expires_at=NOW + timedelta(days=10))
    rejection = store.block("rejection", reason="Still unsuitable")
    cooldown = store.block("cooldown", expires_at=NOW + timedelta(days=2))
    store.prospect = Prospect(
        uuid4(),
        store.business.id,
        store.recommendation.company_id,
        ProspectStage("won_client"),
        NOW,
        NOW,
    )
    store.pending_offer = pending_offer(store, "sending")
    recommendation_before = store.recommendation

    result = service(store).execute(store.principal, request(pause))

    cleared = next(block for block in store.suppression_blocks if block.id == pause.id)
    assert cleared.cleared_at == NOW + timedelta(minutes=5)
    assert cleared.cleared_by_user_id == store.principal.user_id
    assert (
        next(
            block for block in store.suppression_blocks if block.id == rejection.id
        ).cleared_at
        is None
    )
    assert (
        next(
            block for block in store.suppression_blocks if block.id == cooldown.id
        ).cleared_at
        is None
    )
    assert store.recommendation == recommendation_before
    assert store.prospect.stage.value == "won_client"
    assert set(result.remaining_blockers) == {
        "rejected",
        "cooldown",
        "relationship",
        "pending_delivery",
    }
    assert store.commits == 1 and len(store.receipts) == 1


def test_cancel_pause_retry_replays_without_second_clear():
    store = ProspectingCommandStore()
    pause = store.block("pause", expires_at=NOW + timedelta(days=3))
    command = request(pause)
    original = service(store).execute(store.principal, command)
    replay = service(store).execute(store.principal, command)
    assert replay == original
    assert store.commits == 1
    assert len(store.suppression_blocks) == 1
    assert store.suppression_blocks[0].version == 2


def test_cancel_pause_rejects_expired_foreign_wrong_kind_or_stale_block():
    store = ProspectingCommandStore()
    expired = store.block(
        "pause",
        created_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(seconds=1),
    )
    foreign = store.block(
        "pause", business_id=uuid4(), expires_at=NOW + timedelta(days=1)
    )
    rejection = store.block("rejection")
    active = store.block("pause", expires_at=NOW + timedelta(days=1))
    with pytest.raises(ConflictError):
        service(store).execute(store.principal, request(expired))
    with pytest.raises(NotFoundError):
        service(store).execute(store.principal, request(foreign))
    with pytest.raises(ConflictError):
        service(store).execute(store.principal, request(rejection))
    with pytest.raises(ConflictError):
        service(store).execute(
            store.principal, request(active, version=active.version + 1)
        )
    assert all(block.cleared_at is None for block in store.suppression_blocks)
    assert store.receipts == {}
    assert store.commits == 0
