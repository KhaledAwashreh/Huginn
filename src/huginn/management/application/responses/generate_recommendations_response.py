from dataclasses import dataclass
from uuid import UUID

from huginn.management.application.read_models.generated_recommendation_reference import (
    GeneratedRecommendationReference,
)


@dataclass(frozen=True)
class GenerateRecommendationsResponse:
    business_id: UUID
    run_id: UUID
    references: tuple[GeneratedRecommendationReference, ...]
