"""Business-owned prospecting query boundary; ADR-0019."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

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
from huginn.management.domain.value_objects.common import Page
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)


class ProspectingQuery(Protocol):
    def list_recommendations(
        self,
        business_id: UUID,
        request: ListProspectingRequest,
        status: RecommendationStatus | None,
        at: datetime,
    ) -> Page[RecommendationView]: ...
    def get_recommendation(
        self,
        business_id: UUID,
        recommendation_id: UUID,
        at: datetime,
        assessment_revision_id: UUID | None = None,
    ) -> RecommendationView | None: ...
    def list_prospects(
        self,
        business_id: UUID,
        request: ListProspectingRequest,
        stage: ProspectStage | None,
        at: datetime,
    ) -> Page[ProspectView]: ...
    def get_prospect(
        self, business_id: UUID, prospect_id: UUID, at: datetime
    ) -> ProspectView | None: ...
    def list_manageable_suppressions(
        self, business_id: UUID, request: ListProspectingRequest, at: datetime
    ) -> Page[ManageableSuppressionView]: ...
