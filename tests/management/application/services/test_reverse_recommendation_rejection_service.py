from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from huginn.management.application.requests.reverse_recommendation_rejection_request import (
    ReverseRecommendationRejectionRequest,
)
from huginn.management.application.services.reverse_recommendation_rejection_service import (
    ReverseRecommendationRejectionService,
)
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from tests.management.application.services.prospecting_command_store import (
    NOW,
    ProspectingCommandStore,
    pending_offer,
)


def service(store):
    return ReverseRecommendationRejectionService(
        store.uow, clock=lambda: NOW + timedelta(minutes=4)
    )


def request(block, *, key="reverse-rejection", version=None):
    return ReverseRecommendationRejectionRequest(
        suppression_block_id=block.id,
        expected_version=block.version if version is None else version,
        request_key=key,
    )


def test_reverse_clears_only_target_rejection_and_reports_remaining_blocks():
    store = ProspectingCommandStore()
    rejection = store.block("rejection", reason="Wrong buyer")
    pause = store.block("pause", expires_at=NOW + timedelta(days=5))
    cooldown = store.block("cooldown", expires_at=NOW + timedelta(days=3))
    store.prospect = Prospect(
        uuid4(),
        store.business.id,
        store.recommendation.company_id,
        ProspectStage("contacted"),
        NOW,
        NOW,
        version=3,
        notes="Keep this relationship",
    )
    store.pending_offer = pending_offer(store, "unknown")
    recommendation_before = store.recommendation

    result = service(store).execute(store.principal, request(rejection))

    cleared = next(
        block for block in store.suppression_blocks if block.id == rejection.id
    )
    assert cleared.cleared_at == NOW + timedelta(minutes=4)
    assert cleared.cleared_by_user_id == store.principal.user_id
    assert (
        next(
            block for block in store.suppression_blocks if block.id == pause.id
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
    assert store.prospect.stage.value == "contacted"
    assert set(result.remaining_blockers) == {
        "paused",
        "cooldown",
        "relationship",
        "uncertain_delivery",
    }
    assert store.commits == 1 and len(store.receipts) == 1


def test_reversal_receipt_replay_and_hidden_unsaved_company_have_no_side_effects():
    store = ProspectingCommandStore()
    rejection = store.block("rejection", reason="Unsuitable")
    store.recommendation = replace(
        store.recommendation,
        status=RecommendationStatus("rejected"),
        resolved_at=NOW,
        resolved_by_user_id=store.principal.user_id,
        resolution_reason="not_relevant: Unsuitable",
        version=5,
    )
    original_resolution = store.recommendation
    command = request(rejection)
    original = service(store).execute(store.principal, command)
    replay = service(store).execute(store.principal, command)
    assert replay == original
    assert store.prospect is None
    assert store.recommendation == original_resolution
    assert store.commits == 1
    assert len(store.suppression_blocks) == 1


def test_reversal_rejects_foreign_block_wrong_kind_and_stale_version():
    store = ProspectingCommandStore()
    own = store.block("rejection")
    foreign = store.block("rejection", business_id=uuid4())
    pause = store.block("pause", expires_at=NOW + timedelta(days=1))
    with pytest.raises(NotFoundError):
        service(store).execute(store.principal, request(foreign))
    with pytest.raises(ConflictError):
        service(store).execute(store.principal, request(pause))
    with pytest.raises(ConflictError):
        service(store).execute(store.principal, request(own, version=own.version + 1))
    assert all(block.cleared_at is None for block in store.suppression_blocks)
    assert store.receipts == {}
    assert store.commits == 0


def test_reversal_rechecks_after_lock_before_clearing():
    store = ProspectingCommandStore()
    rejection = store.block("rejection")
    store.after_lock = lambda: store.suppression_blocks.__setitem__(
        0, replace(rejection, version=rejection.version + 1)
    )
    with pytest.raises(ConflictError):
        service(store).execute(store.principal, request(rejection))
    assert store.suppression_blocks[0].cleared_at is None
    assert store.receipts == {}
    assert store.commits == 0
