from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)


class RecommendationRepository(Protocol):
    def get_owned(
        self, business_id: UUID, recommendation_id: UUID
    ) -> Recommendation | None: ...
    def get_open(
        self, business_id: UUID, company_id: UUID
    ) -> Recommendation | None: ...
    def create_open(self, recommendation: Recommendation) -> Recommendation:
        """Create/reuse the only open Business/Company occurrence; history may repeat."""
        ...

    def select_current_revision(
        self,
        business_id: UUID,
        recommendation_id: UUID,
        revision_id: UUID,
        expected_version: int,
    ) -> Recommendation:
        """Select a previously appended revision in the same UOW transaction."""
        ...

    def record_confirmed_presentation(
        self,
        business_id: UUID,
        company_id: UUID,
        recommendation_id: UUID,
        cycle_id: UUID,
        revision_id: UUID,
        presented_at: datetime,
    ) -> Recommendation:
        """Set first presentation once from the exact confirmed cycle/revision."""
        ...

    def resolve_owned(
        self,
        business_id: UUID,
        recommendation_id: UUID,
        expected_version: int,
        status: RecommendationStatus,
        actor_user_id: UUID,
        resolved_at: datetime,
        reason: str | None,
    ) -> Recommendation: ...
