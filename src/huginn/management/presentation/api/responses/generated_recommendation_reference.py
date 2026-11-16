"""Exact committed selection, independent of a batch lifecycle."""

from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class GeneratedRecommendationReferenceResponse(ResponseModel):
    recommendation_id: UUID
    revision_id: UUID
    recommendation_version: int
