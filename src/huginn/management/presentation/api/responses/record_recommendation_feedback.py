"""Append-only feedback attribution to the assessment actually shown."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.requests.recommendation_quality_feedback import (
    RecommendationQualityFeedbackRequest,
)
from huginn.management.presentation.api.responses.common import ResponseModel


class RecordRecommendationFeedbackResponse(ResponseModel):
    id: UUID
    business_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    actor_user_id: UUID
    recorded_at: datetime
    feedback: RecommendationQualityFeedbackRequest
