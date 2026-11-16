from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.activity_kind import ActivityKind


def test_activity_keeps_actor_and_occurrence_separate_from_recorded_time():
    occurred = datetime(2026, 12, 20, tzinfo=UTC)
    recorded = datetime(2027, 1, 1, tzinfo=UTC)
    activity = ProspectActivity(
        id=uuid4(),
        business_id=uuid4(),
        prospect_id=uuid4(),
        actor_user_id=uuid4(),
        kind=ActivityKind("stage_changed"),
        occurred_at=occurred,
        recorded_at=recorded,
        payload={"from": "saved", "to": "contacted"},
    )
    assert activity.actor_user_id
    assert activity.occurred_at == occurred
    assert activity.recorded_at == recorded


def test_corrections_append_reference_instead_of_rewriting_prior_activity():
    with pytest.raises(ValidationDomainError):
        ProspectActivity(
            id=uuid4(),
            business_id=uuid4(),
            prospect_id=uuid4(),
            actor_user_id=uuid4(),
            kind=ActivityKind("correction"),
            occurred_at=datetime.now(UTC),
            recorded_at=datetime.now(UTC),
            payload={"corrected": "date"},
        )
