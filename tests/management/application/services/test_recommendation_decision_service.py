from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from huginn.management.application.requests.cancel_recommendation_pause_request import (
    CancelRecommendationPauseRequest,
)
from huginn.management.application.requests.later_recommendation_request import (
    LaterRecommendationRequest,
)
from huginn.management.application.requests.mark_recommendation_not_relevant_request import (
    MarkRecommendationNotRelevantRequest,
)
from huginn.management.application.requests.reverse_recommendation_rejection_request import (
    ReverseRecommendationRejectionRequest,
)
from huginn.management.application.services.recommendation_decision_service import (
    RecommendationDecisionService,
)
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.pause_choice import PauseChoice
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from tests.management.application.services.prospecting_command_store import (
    NOW,
    ProspectingCommandStore,
    pending_offer,
)


def test_one_decision_service_keeps_distinct_action_receipts_and_independent_blocks():
    store = ProspectingCommandStore()
    pause = store.block("pause", expires_at=NOW + timedelta(days=3))
    rejection = store.block("rejection")
    service = RecommendationDecisionService(
        store.uow, clock=lambda: NOW + timedelta(minutes=1)
    )
    cancel = CancelRecommendationPauseRequest(pause.id, pause.version, "cancel")
    cancelled = service.cancel_pause(store.principal, cancel)
    with pytest.raises(ConflictError):
        service.reverse_rejection(
            store.principal,
            ReverseRecommendationRejectionRequest(
                rejection.id, rejection.version, "cancel"
            ),
        )
    assert store.suppression_blocks[1].cleared_at is None
    reverse = ReverseRecommendationRejectionRequest(
        rejection.id, rejection.version, "reverse"
    )
    reversed_result = service.reverse_rejection(store.principal, reverse)
    assert service.cancel_pause(store.principal, cancel) == cancelled
    assert service.reverse_rejection(store.principal, reverse) == reversed_result
    assert store.commits == 2
    assert len(store.receipts) == 2
    assert cancelled.remaining_blockers == ("rejected",)
    assert reversed_result.remaining_blockers == ()


def _later_request(store, choice="x1", *, key="later-1", expected_pause=None):
    return LaterRecommendationRequest(
        recommendation_id=store.recommendation.id,
        assessment_revision_id=store.revision.id,
        expected_recommendation_version=store.recommendation.version,
        pause_choice=PauseChoice(choice),
        expected_repeat_interval_days=store.preferences.repeat_interval_days,
        expected_preference_updated_at=store.preferences.updated_at,
        expected_pause_id=expected_pause.id if expected_pause else None,
        expected_pause_version=expected_pause.version if expected_pause else None,
        request_key=key,
    )


def _later_service(store):
    return RecommendationDecisionService(
        store.uow, clock=lambda: NOW + timedelta(minutes=3)
    )


@pytest.mark.parametrize(
    ("choice", "days"),
    [("x1", 30), ("x2", 60), ("x3", 90), ("x4", 120), ("indefinite", None)],
)
def test_later_later_replaces_only_expected_pause_and_snapshots_choice(choice, days):
    store = ProspectingCommandStore()
    previous = store.block("pause", expires_at=NOW + timedelta(days=7))
    rejection = store.block("rejection", reason="Still excluded")
    cooldown = store.block("cooldown", expires_at=NOW + timedelta(days=5))
    result = _later_service(store).later(
        store.principal, _later_request(store, choice, expected_pause=previous)
    )
    updated_previous = next(
        block for block in store.suppression_blocks if block.id == previous.id
    )
    replacement = next(
        block
        for block in store.suppression_blocks
        if block.id == result.suppression_block_id
    )
    assert updated_previous.cleared_at == NOW + timedelta(minutes=3)
    assert updated_previous.cleared_by_user_id == store.principal.user_id
    assert replacement.kind.value == "pause"
    assert replacement.created_at == NOW + timedelta(minutes=3)
    assert replacement.expires_at == (
        NOW + timedelta(minutes=3) + timedelta(days=days) if days else None
    )
    assert store.recommendation.status.value == "open"
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
    assert "rejected" in result.remaining_blockers
    assert "cooldown" in result.remaining_blockers
    assert "paused" in result.remaining_blockers
    assert result.pause_choice == choice
    assert result.repeat_interval_days == 30
    assert result.preference_updated_at == NOW
    assert len(store.receipts) == 1 and store.commits == 1


def test_later_later_same_key_replays_and_does_not_replace_twice():
    store = ProspectingCommandStore()
    old_pause = store.block("pause", expires_at=NOW + timedelta(days=10))
    command = _later_request(store, "x2", expected_pause=old_pause)
    original = _later_service(store).later(store.principal, command)
    store.preferences = replace(store.preferences, repeat_interval_days=60)
    replay = _later_service(store).later(store.principal, command)
    assert replay == original
    assert store.commits == 1
    assert len(store.suppression_blocks) == 2
    assert len(store.receipts) == 1


def test_later_later_rejects_stale_preferences_expected_pause_or_multiple_active_pauses():
    store = ProspectingCommandStore()
    first_pause = store.block("pause", expires_at=NOW + timedelta(days=5))
    store.block("pause", expires_at=NOW + timedelta(days=8))
    command = _later_request(store, "x1", expected_pause=first_pause)
    with pytest.raises(ConflictError):
        _later_service(store).later(store.principal, command)
    assert all(block.cleared_at is None for block in store.suppression_blocks)
    assert store.commits == 0
    store = ProspectingCommandStore()
    store.preferences = replace(store.preferences, repeat_interval_days=45)
    stale_preferences = replace(
        _later_request(store, "x2"),
        expected_repeat_interval_days=30,
        expected_preference_updated_at=NOW,
    )
    with pytest.raises(ConflictError):
        _later_service(store).later(store.principal, stale_preferences)
    assert store.suppression_blocks == []
    assert store.receipts == {}
    store = ProspectingCommandStore()
    active = store.block("pause", expires_at=NOW + timedelta(days=4))
    with pytest.raises(ConflictError):
        _later_service(store).later(
            store.principal, _later_request(store, "x1", expected_pause=None)
        )
    assert store.suppression_blocks == [active]


def test_later_later_revalidates_after_pair_lock_and_receipt_failure_rolls_back_replacement():
    store = ProspectingCommandStore()
    old_pause = store.block("pause", expires_at=NOW + timedelta(days=10))
    command = _later_request(store, "x2", expected_pause=old_pause)
    store.after_lock = lambda: store.block("pause", expires_at=NOW + timedelta(days=12))
    with pytest.raises(ConflictError):
        _later_service(store).later(store.principal, command)
    assert all(block.cleared_at is None for block in store.suppression_blocks)
    assert store.receipts == {}
    store = ProspectingCommandStore()
    old_pause = store.block("pause", expires_at=NOW + timedelta(days=10))
    store.fail_receipt = True
    with pytest.raises(ConflictError):
        _later_service(store).later(
            store.principal, _later_request(store, "x2", expected_pause=old_pause)
        )
    assert store.suppression_blocks == [old_pause]
    assert store.receipts == {}
    assert store.commits == 0


def _mark_not_relevant_request(
    store, *, key="reject-1", version=None, revision_id=None, reason=None
):
    return MarkRecommendationNotRelevantRequest(
        recommendation_id=store.recommendation.id,
        assessment_revision_id=revision_id or store.revision.id,
        expected_recommendation_version=store.recommendation.version
        if version is None
        else version,
        reason=reason,
        request_key=key,
    )


def _mark_not_relevant_service(store):
    return RecommendationDecisionService(
        store.uow, clock=lambda: NOW + timedelta(minutes=2)
    )


def test_mark_not_relevant_rejection_resolves_exact_open_occurrence_and_appends_one_owned_block():
    store = ProspectingCommandStore()
    store.block("cooldown", expires_at=NOW + timedelta(days=4))
    result = _mark_not_relevant_service(store).mark_not_relevant(
        store.principal, _mark_not_relevant_request(store, reason="Wrong buyer")
    )
    assert store.recommendation.status == RecommendationStatus("rejected")
    assert store.recommendation.version == 5
    assert store.recommendation.resolved_by_user_id == store.principal.user_id
    assert store.recommendation.resolved_at == NOW + timedelta(minutes=2)
    assert store.recommendation.resolution_reason == "not_relevant: Wrong buyer"
    rejection = next(
        block for block in store.suppression_blocks if block.kind.value == "rejection"
    )
    assert rejection.created_by_user_id == store.principal.user_id
    assert rejection.reason == "Wrong buyer"
    assert rejection.expires_at is None
    assert result.recommendation_status == "rejected"
    assert result.suppression_block_id == rejection.id
    assert set(result.remaining_blockers) == {"rejected", "cooldown"}
    assert not store.prospect and store.commits == 1
    assert len(store.receipts) == 1


def test_mark_not_relevant_same_key_replays_and_changed_intent_or_foreign_membership_writes_nothing():
    store = ProspectingCommandStore()
    command = _mark_not_relevant_request(store)
    original = _mark_not_relevant_service(store).mark_not_relevant(
        store.principal, command
    )
    replay = _mark_not_relevant_service(store).mark_not_relevant(
        store.principal, command
    )
    assert replay == original
    assert store.commits == 1
    assert (
        len(
            [
                block
                for block in store.suppression_blocks
                if block.kind.value == "rejection"
            ]
        )
        == 1
    )
    with pytest.raises(ConflictError):
        _mark_not_relevant_service(store).mark_not_relevant(
            store.principal,
            _mark_not_relevant_request(
                store, key=command.request_key, reason="changed"
            ),
        )
    with pytest.raises(NotFoundError):
        _mark_not_relevant_service(store).mark_not_relevant(
            replace(store.principal, user_id=uuid4()),
            _mark_not_relevant_request(store, key="foreign-owner"),
        )
    assert len(store.suppression_blocks) == 1
    assert len(store.receipts) == 1
    assert store.commits == 1


def test_mark_not_relevant_recommendation_is_revalidated_after_lock_and_optimistic_version_is_enforced():
    store = ProspectingCommandStore()
    store.after_lock = lambda: setattr(
        store, "recommendation", replace(store.recommendation, version=5)
    )
    with pytest.raises(ConflictError):
        _mark_not_relevant_service(store).mark_not_relevant(
            store.principal, _mark_not_relevant_request(store)
        )
    assert store.recommendation.status.value == "open"
    assert store.suppression_blocks == []
    assert store.receipts == {}
    assert store.commits == 0


def test_mark_not_relevant_missing_shown_revision_is_not_resolved():
    store = ProspectingCommandStore()
    with pytest.raises(NotFoundError):
        _mark_not_relevant_service(store).mark_not_relevant(
            store.principal, _mark_not_relevant_request(store, revision_id=uuid4())
        )
    assert store.recommendation.status.value == "open"
    assert store.suppression_blocks == []


def _cancel_pause_service(store):
    return RecommendationDecisionService(
        store.uow, clock=lambda: NOW + timedelta(minutes=5)
    )


def _cancel_pause_request(block, *, key="cancel-pause", version=None):
    return CancelRecommendationPauseRequest(
        suppression_block_id=block.id,
        expected_version=block.version if version is None else version,
        request_key=key,
    )


def test_cancel_pause_cancel_clears_only_the_selected_pause_and_discloses_other_blocks():
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
    result = _cancel_pause_service(store).cancel_pause(
        store.principal, _cancel_pause_request(pause)
    )
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


def test_cancel_pause_cancel_pause_retry_replays_without_second_clear():
    store = ProspectingCommandStore()
    pause = store.block("pause", expires_at=NOW + timedelta(days=3))
    command = _cancel_pause_request(pause)
    original = _cancel_pause_service(store).cancel_pause(store.principal, command)
    replay = _cancel_pause_service(store).cancel_pause(store.principal, command)
    assert replay == original
    assert store.commits == 1
    assert len(store.suppression_blocks) == 1
    assert store.suppression_blocks[0].version == 2


def test_cancel_pause_cancel_pause_rejects_expired_foreign_wrong_kind_or_stale_block():
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
        _cancel_pause_service(store).cancel_pause(
            store.principal, _cancel_pause_request(expired)
        )
    with pytest.raises(NotFoundError):
        _cancel_pause_service(store).cancel_pause(
            store.principal, _cancel_pause_request(foreign)
        )
    with pytest.raises(ConflictError):
        _cancel_pause_service(store).cancel_pause(
            store.principal, _cancel_pause_request(rejection)
        )
    with pytest.raises(ConflictError):
        _cancel_pause_service(store).cancel_pause(
            store.principal, _cancel_pause_request(active, version=active.version + 1)
        )
    assert all(block.cleared_at is None for block in store.suppression_blocks)
    assert store.receipts == {}
    assert store.commits == 0


def _reverse_rejection_service(store):
    return RecommendationDecisionService(
        store.uow, clock=lambda: NOW + timedelta(minutes=4)
    )


def _reverse_rejection_request(block, *, key="reverse-rejection", version=None):
    return ReverseRecommendationRejectionRequest(
        suppression_block_id=block.id,
        expected_version=block.version if version is None else version,
        request_key=key,
    )


def test_reverse_rejection_reverse_clears_only_target_rejection_and_reports_remaining_blocks():
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
    result = _reverse_rejection_service(store).reverse_rejection(
        store.principal, _reverse_rejection_request(rejection)
    )
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


def test_reverse_rejection_reversal_receipt_replay_and_hidden_unsaved_company_have_no_side_effects():
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
    command = _reverse_rejection_request(rejection)
    original = _reverse_rejection_service(store).reverse_rejection(
        store.principal, command
    )
    replay = _reverse_rejection_service(store).reverse_rejection(
        store.principal, command
    )
    assert replay == original
    assert store.prospect is None
    assert store.recommendation == original_resolution
    assert store.commits == 1
    assert len(store.suppression_blocks) == 1


def test_reverse_rejection_reversal_rejects_foreign_block_wrong_kind_and_stale_version():
    store = ProspectingCommandStore()
    own = store.block("rejection")
    foreign = store.block("rejection", business_id=uuid4())
    pause = store.block("pause", expires_at=NOW + timedelta(days=1))
    with pytest.raises(NotFoundError):
        _reverse_rejection_service(store).reverse_rejection(
            store.principal, _reverse_rejection_request(foreign)
        )
    with pytest.raises(ConflictError):
        _reverse_rejection_service(store).reverse_rejection(
            store.principal, _reverse_rejection_request(pause)
        )
    with pytest.raises(ConflictError):
        _reverse_rejection_service(store).reverse_rejection(
            store.principal, _reverse_rejection_request(own, version=own.version + 1)
        )
    assert all(block.cleared_at is None for block in store.suppression_blocks)
    assert store.receipts == {}
    assert store.commits == 0


def test_reverse_rejection_reversal_rechecks_after_lock_before_clearing():
    store = ProspectingCommandStore()
    rejection = store.block("rejection")
    store.after_lock = lambda: store.suppression_blocks.__setitem__(
        0, replace(rejection, version=rejection.version + 1)
    )
    with pytest.raises(ConflictError):
        _reverse_rejection_service(store).reverse_rejection(
            store.principal, _reverse_rejection_request(rejection)
        )
    assert store.suppression_blocks[0].cleared_at is None
    assert store.receipts == {}
    assert store.commits == 0
