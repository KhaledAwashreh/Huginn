"""Clear one exact independently versioned suppression block."""

from typing import Annotated

from pydantic import Field

from huginn.management.presentation.api.requests.common import NonBlank, RequestModel


class ClearRecommendationSuppressionRequest(RequestModel):
    expected_version: Annotated[int, Field(ge=1)]
    request_key: NonBlank
