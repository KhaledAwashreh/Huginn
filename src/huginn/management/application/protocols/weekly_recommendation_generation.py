"""Shared Business-owned recommendation generation used by scheduled delivery."""

from typing import Protocol
from uuid import UUID

from huginn.management.application.responses.generate_recommendations_response import (
    GenerateRecommendationsResponse,
)


class WeeklyRecommendationGeneration(Protocol):
    def execute_weekly(self, business_id: UUID) -> GenerateRecommendationsResponse:
        """Refresh valid active strategies and return exact selected revisions."""
        ...
