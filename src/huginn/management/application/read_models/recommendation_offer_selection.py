"""Current Company inputs validated against an immutable selected revision."""

from dataclasses import dataclass

from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.recommendation import Recommendation


@dataclass(frozen=True, slots=True)
class RecommendationOfferSelection:
    recommendation: Recommendation
    revision: AssessmentRevision
    company: RecommendationCompany
