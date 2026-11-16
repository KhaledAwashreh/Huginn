"""Immutable Save command receipt; newer prospect state is read separately."""

from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class SaveRecommendationResponse(ResponseModel):
    prospect_id: UUID
    company_id: UUID
    prospect_stage: str
    prospect_version: int
    origin_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    recommendation_status: str
