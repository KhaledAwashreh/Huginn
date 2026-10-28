from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.requests.recommendation_feedback import (
    RecommendationFeedbackRequest,
)


class RecommendationFeedbackResponse(RecommendationFeedbackRequest):
    id: UUID
    batch_id: UUID
    created_at: datetime
