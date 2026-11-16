from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)


def test_recommendation_is_business_company_scoped_and_open_until_explicit_resolution():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    recommendation = Recommendation(
        id=uuid4(),
        business_id=uuid4(),
        company_id=uuid4(),
        status=RecommendationStatus("open"),
        created_at=now,
        updated_at=now,
    )
    assert recommendation.first_presented_at is None
    assert recommendation.current_revision_id is None


def test_resolved_recommendation_keeps_actor_and_time_without_generic_closed_state():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        RecommendationStatus("closed")
    with pytest.raises(ValidationDomainError):
        Recommendation(
            id=uuid4(),
            business_id=uuid4(),
            company_id=uuid4(),
            status=RecommendationStatus("converted"),
            created_at=now,
            updated_at=now,
            resolved_at=now,
        )
    resolved = Recommendation(
        id=uuid4(),
        business_id=uuid4(),
        company_id=uuid4(),
        status=RecommendationStatus("rejected"),
        created_at=now,
        updated_at=now,
        resolved_at=now,
        resolved_by_user_id=uuid4(),
        resolution_reason="Not relevant",
    )
    assert resolved.status.value == "rejected"
    assert resolved.resolved_by_user_id is not None
