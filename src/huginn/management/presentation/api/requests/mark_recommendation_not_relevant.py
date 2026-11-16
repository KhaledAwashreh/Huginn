"""Versioned rejection of the exact shown assessment."""

from typing import Annotated

from pydantic import Field

from huginn.management.presentation.api.requests.save_recommendation import (
    SaveRecommendationRequest,
)


class MarkRecommendationNotRelevantRequest(SaveRecommendationRequest):
    expected_recommendation_version: Annotated[int, Field(ge=1)]
    reason: str | None = None
