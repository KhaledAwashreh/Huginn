"""Business recommendation preferences persistence contract."""

from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.business_recommendation_preferences import (
    BusinessRecommendationPreferences,
)
from huginn.management.domain.value_objects.business_recommendation_preferences import (
    BusinessRecommendationPreferencesChanges,
)


class BusinessRecommendationPreferencesRepository(Protocol):
    def get(self, business_id: UUID) -> BusinessRecommendationPreferences | None: ...
    def update(
        self,
        business_id: UUID,
        changes: BusinessRecommendationPreferencesChanges,
    ) -> BusinessRecommendationPreferences | None: ...
