"""Strict HTTP intent for clear prospect follow up."""

from typing import Annotated

from pydantic import Field

from huginn.management.presentation.api.requests.common import (
    NonBlank,
    RequestModel,
    RequestTimestamp,
)


class ClearProspectFollowUpRequest(RequestModel):
    expected_version: Annotated[int, Field(ge=1)]
    request_key: NonBlank
    occurred_at: RequestTimestamp
