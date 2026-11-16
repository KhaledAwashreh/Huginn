"""Request an owned preparation claim without recording presentation."""

from typing import Annotated

from pydantic import Field

from huginn.management.presentation.api.requests.common import RequestModel, RequestUUID


class PrepareRecommendationOfferRequest(RequestModel):
    assessment_revision_id: RequestUUID
    request_key: Annotated[str, Field(min_length=1, max_length=200)]
