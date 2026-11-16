from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.policies.prospect_activity_occurrence import (
    project_activity_occurrence,
)
from huginn.management.domain.value_objects.activity_kind import ActivityKind

NOW = datetime(2026, 11, 14, tzinfo=UTC)


def _activity(
    kind,
    occurred_at,
    recorded_at,
    *,
    business_id=None,
    prospect_id=None,
    correction_of_id=None,
    payload=None,
):
    return ProspectActivity(
        uuid4(),
        business_id or uuid4(),
        prospect_id or uuid4(),
        uuid4(),
        ActivityKind(kind),
        occurred_at,
        recorded_at,
        payload or {},
        correction_of_id,
    )


def test_correction_projection_uses_contiguous_sequence_not_uuid_ties():
    original = _activity(
        "proposal_sent", NOW - timedelta(days=2), NOW - timedelta(days=1)
    )
    first = _activity(
        "correction",
        NOW,
        NOW,
        business_id=original.business_id,
        prospect_id=original.prospect_id,
        correction_of_id=original.id,
        payload={
            "prior": (NOW - timedelta(days=2)).isoformat(),
            "replacement": (NOW - timedelta(days=3)).isoformat(),
            "correction_sequence": 1,
        },
    )
    second = _activity(
        "correction",
        NOW + timedelta(seconds=1),
        NOW,
        business_id=original.business_id,
        prospect_id=original.prospect_id,
        correction_of_id=original.id,
        payload={
            "prior": (NOW - timedelta(days=3)).isoformat(),
            "replacement": (NOW - timedelta(days=4)).isoformat(),
            "correction_sequence": 2,
        },
    )

    result = project_activity_occurrence(original, (second, original, first))

    assert result.original_activity_id == original.id
    assert result.effective_occurred_at == NOW - timedelta(days=4)
    assert result.correction_head_id == second.id
    assert result.correction_sequence == 2


def test_correction_projection_rejects_a_gap_or_wrong_prior_value():
    original = _activity("note_added", NOW, NOW)
    bad = _activity(
        "correction",
        NOW,
        NOW,
        business_id=original.business_id,
        prospect_id=original.prospect_id,
        correction_of_id=original.id,
        payload={
            "prior": (NOW - timedelta(days=1)).isoformat(),
            "replacement": (NOW - timedelta(days=2)).isoformat(),
            "correction_sequence": 2,
        },
    )

    with pytest.raises(ValidationDomainError):
        project_activity_occurrence(original, (bad,))


def test_correction_projection_requires_an_original_activity():
    correction = _activity(
        "correction",
        NOW,
        NOW,
        correction_of_id=uuid4(),
        payload={"prior": NOW.isoformat(), "replacement": NOW.isoformat()},
    )

    with pytest.raises(ValidationDomainError):
        project_activity_occurrence(correction, (correction,))
