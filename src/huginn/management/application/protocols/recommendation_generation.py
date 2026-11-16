from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.application.protocols.business_company_state_query import (
    BusinessCompanyStateQuery,
)
from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.application.read_models.recommendation_profile import (
    RecommendationProfile,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)


class RecommendationGenerationSource(BusinessCompanyStateQuery, Protocol):
    def lock_successful_run_window(self, business_id: UUID) -> None: ...
    def successful_on_demand_runs_since(
        self, business_id: UUID, since: datetime
    ) -> tuple[datetime, ...]: ...
    def profile(
        self, owner_user_id: UUID, strategy_id: UUID
    ) -> RecommendationProfile | None: ...
    def active_profiles(
        self, owner_user_id: UUID
    ) -> tuple[RecommendationProfile, ...]: ...
    def candidates(
        self,
        terms: tuple[str, ...],
        cutoff: datetime,
        as_of: datetime,
        limit: int = 200,
        *,
        exclude_company_ids: frozenset[UUID] = frozenset(),
        offset: int = 0,
    ) -> tuple[RecommendationCompany, ...]: ...
    def candidate_is_current(
        self, company: RecommendationCompany, cutoff: datetime, as_of: datetime
    ) -> bool: ...
    def current_company_for_revision(
        self, revision: AssessmentRevision, as_of: datetime
    ) -> RecommendationCompany | None: ...
    def was_selected_in_generation(
        self, business_id: UUID, recommendation_id: UUID, revision_id: UUID
    ) -> bool: ...

    def company_states(
        self,
        business_id: UUID,
        company_ids: tuple[UUID, ...],
        as_of: datetime,
        *,
        exclude_offer_cycle_id: UUID | None = None,
    ) -> tuple[BusinessCompanyState, ...]: ...
