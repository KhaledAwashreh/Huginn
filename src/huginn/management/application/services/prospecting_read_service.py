"""Owner-isolated reads without ranking, claims or workflow mutations."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from huginn.management.application.protocols.prospecting_query import (
    ProspectingQuery,
    RecommendationListStatus,
)
from huginn.management.application.read_models.manageable_suppression_view import (
    ManageableSuppressionView,
)
from huginn.management.application.read_models.prospect_view import ProspectView
from huginn.management.application.read_models.recommendation_view import (
    RecommendationView,
)
from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import Page, Principal
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

_OPEN = RecommendationStatus("open")


class ProspectingReadService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        query_factory: Callable[[ProspectingUnitOfWork], ProspectingQuery],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._work = unit_of_work_factory
        self._query = query_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def list_recommendations(
        self,
        principal: Principal,
        request: ListProspectingRequest,
        *,
        status: RecommendationListStatus = _OPEN,
        strategy_id: UUID | None = None,
    ) -> Page[RecommendationView]:
        with self._work() as work:
            business = business_id_for_principal(principal, work.businesses)
            return self._query(work).list_recommendations(
                business, request, status, self._clock(), strategy_id
            )

    def get_recommendation(
        self,
        principal: Principal,
        recommendation_id: UUID,
        *,
        assessment_revision_id: UUID | None = None,
    ) -> RecommendationView:
        with self._work() as work:
            business = business_id_for_principal(principal, work.businesses)
            value = self._query(work).get_recommendation(
                business, recommendation_id, self._clock(), assessment_revision_id
            )
            if value is None:
                raise NotFoundError("Recommendation not found")
            return value

    def list_prospects(
        self,
        principal: Principal,
        request: ListProspectingRequest,
        *,
        stage: ProspectStage | None = None,
    ) -> Page[ProspectView]:
        with self._work() as work:
            business = business_id_for_principal(principal, work.businesses)
            return self._query(work).list_prospects(
                business, request, stage, self._clock()
            )

    def get_prospect(self, principal: Principal, prospect_id: UUID) -> ProspectView:
        with self._work() as work:
            business = business_id_for_principal(principal, work.businesses)
            value = self._query(work).get_prospect(business, prospect_id, self._clock())
            if value is None:
                raise NotFoundError("Prospect not found")
            return value

    def list_manageable_suppressions(
        self, principal: Principal, request: ListProspectingRequest
    ) -> Page[ManageableSuppressionView]:
        with self._work() as work:
            business = business_id_for_principal(principal, work.businesses)
            return self._query(work).list_manageable_suppressions(
                business, request, self._clock()
            )

    def list_assessments(
        self, principal: Principal, recommendation_id: UUID
    ) -> tuple[AssessmentRevision, ...]:
        with self._work() as work:
            business = business_id_for_principal(principal, work.businesses)
            if work.recommendations.get_owned(business, recommendation_id) is None:
                raise NotFoundError("Recommendation not found")
            return work.assessment_revisions.list_history(business, recommendation_id)
