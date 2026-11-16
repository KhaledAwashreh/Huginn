"""Exact revision and retry identity for report-only feedback."""

from huginn.management.presentation.api.requests.recommendation_quality_feedback import (
    RecommendationQualityFeedbackRequest,
)
from huginn.management.presentation.api.requests.save_recommendation import (
    SaveRecommendationRequest,
)


class RecordRecommendationFeedbackRequest(SaveRecommendationRequest):
    feedback: RecommendationQualityFeedbackRequest
