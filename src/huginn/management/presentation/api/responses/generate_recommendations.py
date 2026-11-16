"""Generation operation metadata and selected stable recommendation references."""

from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.generated_recommendation_reference import (
    GeneratedRecommendationReferenceResponse,
)


class GenerateRecommendationsResponse(ResponseModel):
    run_id: UUID
    references: list[GeneratedRecommendationReferenceResponse]
