from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from huginn.management.application.requests.mark_recommendation_not_relevant_request import (
    MarkRecommendationNotRelevantRequest,
)
from huginn.management.application.services.mark_recommendation_not_relevant_service import (
    MarkRecommendationNotRelevantService,
)
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from tests.management.application.services.prospecting_command_store import (
    NOW,
    ProspectingCommandStore,
)


def request(store, *, key="reject-1", version=None, revision_id=None, reason=None):
    return MarkRecommendationNotRelevantRequest(
        recommendation_id=store.recommendation.id,
        assessment_revision_id=revision_id or store.revision.id,
        expected_recommendation_version=(
            store.recommendation.version if version is None else version
        ),
        reason=reason,
        request_key=key,
    )


def service(store):
    return MarkRecommendationNotRelevantService(
        store.uow, clock=lambda: NOW + timedelta(minutes=2)
    )


def test_rejection_resolves_exact_open_occurrence_and_appends_one_owned_block():
    store = ProspectingCommandStore()
    store.block("cooldown", expires_at=NOW + timedelta(days=4))

    result = service(store).execute(
        store.principal, request(store, reason="Wrong buyer")
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


def test_same_key_replays_and_changed_intent_or_foreign_membership_writes_nothing():
    store = ProspectingCommandStore()
    command = request(store)
    original = service(store).execute(store.principal, command)
    replay = service(store).execute(store.principal, command)
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
        service(store).execute(
            store.principal, request(store, key=command.request_key, reason="changed")
        )
    with pytest.raises(NotFoundError):
        service(store).execute(
            replace(store.principal, user_id=uuid4()),
            request(store, key="foreign-owner"),
        )
    assert len(store.suppression_blocks) == 1
    assert len(store.receipts) == 1
    assert store.commits == 1


def test_recommendation_is_revalidated_after_lock_and_optimistic_version_is_enforced():
    store = ProspectingCommandStore()
    store.after_lock = lambda: setattr(
        store, "recommendation", replace(store.recommendation, version=5)
    )

    with pytest.raises(ConflictError):
        service(store).execute(store.principal, request(store))

    assert store.recommendation.status.value == "open"
    assert store.suppression_blocks == []
    assert store.receipts == {}
    assert store.commits == 0


def test_missing_shown_revision_is_not_resolved():
    store = ProspectingCommandStore()

    with pytest.raises(NotFoundError):
        service(store).execute(store.principal, request(store, revision_id=uuid4()))

    assert store.recommendation.status.value == "open"
    assert store.suppression_blocks == []
