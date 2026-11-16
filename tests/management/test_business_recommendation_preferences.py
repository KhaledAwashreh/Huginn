from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.application.services.business_recommendation_preferences import (
    BusinessRecommendationPreferencesService,
)
from huginn.management.domain.entities.business import Business
from huginn.management.domain.entities.business_recommendation_preferences import (
    BusinessRecommendationPreferences,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.business_recommendation_preferences import (
    BusinessRecommendationPreferencesChanges,
)
from huginn.management.domain.value_objects.common import Principal


def test_preference_service_resolves_business_from_authenticated_user():
    user_id, business_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    business = Business(
        business_id,
        user_id,
        None,
        None,
        None,
        None,
        None,
        None,
        now,
        now,
    )
    observed = {}

    class UnitOfWork:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def commit(self):
            observed["committed"] = True

    class Businesses:
        def get_by_owner_user_id(self, owner_user_id):
            observed["owner_user_id"] = owner_user_id
            return business

    class Preferences:
        def update(self, owner_business_id, changes):
            observed["business_id"] = owner_business_id
            observed["days"] = changes.repeat_interval_days
            return BusinessRecommendationPreferences(owner_business_id, 45, now)

    service = BusinessRecommendationPreferencesService(
        UnitOfWork,
        businesses_factory=lambda _: Businesses(),
        preferences_factory=lambda _: Preferences(),
    )
    result = service.update(
        Principal(uuid4(), user_id), BusinessRecommendationPreferencesChanges(45)
    )

    assert result.business_id == business_id
    assert observed == {
        "owner_user_id": user_id,
        "business_id": business_id,
        "days": 45,
        "committed": True,
    }


def test_preference_service_rejects_nonpositive_repeat_interval():
    with pytest.raises(ValidationDomainError):
        BusinessRecommendationPreferencesChanges(0)
