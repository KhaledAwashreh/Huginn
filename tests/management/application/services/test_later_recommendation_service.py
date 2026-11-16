from dataclasses import replace
from datetime import timedelta

import pytest

from huginn.management.application.requests.later_recommendation_request import (
    LaterRecommendationRequest,
)
from huginn.management.application.services.later_recommendation_service import (
    LaterRecommendationService,
)
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.pause_choice import PauseChoice
from tests.management.application.services.prospecting_command_store import (
    NOW,
    ProspectingCommandStore,
)


def request(store, choice="x1", *, key="later-1", expected_pause=None):
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


def service(store):
    return LaterRecommendationService(
        store.uow, clock=lambda: NOW + timedelta(minutes=3)
    )


@pytest.mark.parametrize(
    ("choice", "days"),
    [("x1", 30), ("x2", 60), ("x3", 90), ("x4", 120), ("indefinite", None)],
)
def test_later_replaces_only_expected_pause_and_snapshots_choice(choice, days):
    store = ProspectingCommandStore()
    previous = store.block("pause", expires_at=NOW + timedelta(days=7))
    rejection = store.block("rejection", reason="Still excluded")
    cooldown = store.block("cooldown", expires_at=NOW + timedelta(days=5))
    result = service(store).execute(
        store.principal, request(store, choice, expected_pause=previous)
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


def test_later_same_key_replays_and_does_not_replace_twice():
    store = ProspectingCommandStore()
    old_pause = store.block("pause", expires_at=NOW + timedelta(days=10))
    command = request(store, "x2", expected_pause=old_pause)
    original = service(store).execute(store.principal, command)
    store.preferences = replace(store.preferences, repeat_interval_days=60)

    replay = service(store).execute(store.principal, command)

    assert replay == original
    assert store.commits == 1
    assert len(store.suppression_blocks) == 2
    assert len(store.receipts) == 1


def test_later_rejects_stale_preferences_expected_pause_or_multiple_active_pauses():
    store = ProspectingCommandStore()
    first_pause = store.block("pause", expires_at=NOW + timedelta(days=5))
    store.block("pause", expires_at=NOW + timedelta(days=8))
    command = request(store, "x1", expected_pause=first_pause)
    with pytest.raises(ConflictError):
        service(store).execute(store.principal, command)
    assert all(block.cleared_at is None for block in store.suppression_blocks)
    assert store.commits == 0

    store = ProspectingCommandStore()
    store.preferences = replace(store.preferences, repeat_interval_days=45)
    stale_preferences = replace(
        request(store, "x2"),
        expected_repeat_interval_days=30,
        expected_preference_updated_at=NOW,
    )
    with pytest.raises(ConflictError):
        service(store).execute(store.principal, stale_preferences)
    assert store.suppression_blocks == []
    assert store.receipts == {}

    store = ProspectingCommandStore()
    active = store.block("pause", expires_at=NOW + timedelta(days=4))
    with pytest.raises(ConflictError):
        service(store).execute(
            store.principal, request(store, "x1", expected_pause=None)
        )
    assert store.suppression_blocks == [active]


def test_later_revalidates_after_pair_lock_and_receipt_failure_rolls_back_replacement():
    store = ProspectingCommandStore()
    old_pause = store.block("pause", expires_at=NOW + timedelta(days=10))
    command = request(store, "x2", expected_pause=old_pause)
    store.after_lock = lambda: store.block("pause", expires_at=NOW + timedelta(days=12))
    with pytest.raises(ConflictError):
        service(store).execute(store.principal, command)
    assert all(block.cleared_at is None for block in store.suppression_blocks)
    assert store.receipts == {}

    store = ProspectingCommandStore()
    old_pause = store.block("pause", expires_at=NOW + timedelta(days=10))
    store.fail_receipt = True
    with pytest.raises(ConflictError):
        service(store).execute(
            store.principal, request(store, "x2", expected_pause=old_pause)
        )
    assert store.suppression_blocks == [old_pause]
    assert store.receipts == {}
    assert store.commits == 0
