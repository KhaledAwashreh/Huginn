"""The exact assessment the authenticated person chose to save."""

from huginn.management.presentation.api.requests.common import (
    NonBlank,
    RequestModel,
    RequestUUID,
)


class SaveRecommendationRequest(RequestModel):
    assessment_revision_id: RequestUUID
    request_key: NonBlank
