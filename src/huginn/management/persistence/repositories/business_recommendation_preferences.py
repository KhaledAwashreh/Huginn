"""PostgreSQL persistence for business recommendation cadence."""

from uuid import UUID

from huginn.management.domain.entities.business_recommendation_preferences import (
    BusinessRecommendationPreferences,
)
from huginn.management.domain.value_objects.business_recommendation_preferences import (
    BusinessRecommendationPreferencesChanges,
)
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.repositories.business_recommendation_preferences import (
    BusinessRecommendationPreferencesRepository,
)


class PostgresBusinessRecommendationPreferencesRepository(
    BusinessRecommendationPreferencesRepository
):
    _columns = "business_id, repeat_interval_days, updated_at"

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row) -> BusinessRecommendationPreferences:
        return BusinessRecommendationPreferences(*row)

    def get(self, business_id: UUID) -> BusinessRecommendationPreferences | None:
        row = self.connection.execute(
            "SELECT business_id, repeat_interval_days, updated_at "
            "FROM operational.business_recommendation_preferences "
            "WHERE business_id=%s",
            (business_id,),
        ).fetchone()
        return self._map(row) if row else None

    def update(
        self,
        business_id: UUID,
        changes: BusinessRecommendationPreferencesChanges,
    ) -> BusinessRecommendationPreferences | None:
        row = self.connection.execute(
            "UPDATE operational.business_recommendation_preferences "
            "SET repeat_interval_days=%s, updated_at=clock_timestamp() "
            "WHERE business_id=%s RETURNING business_id, repeat_interval_days, updated_at",
            (changes.repeat_interval_days, business_id),
        ).fetchone()
        return self._map(row) if row else None
