"""Strict HTTP intent for set prospect follow up."""

from typing import Annotated

from pydantic import Field

from huginn.management.presentation.api.requests.common import (
    NonBlank,
    RequestModel,
    RequestTimestamp,
)


class SetProspectFollowUpRequest(RequestModel):
    expected_version: Annotated[int, Field(ge=1)]
    request_key: NonBlank
    occurred_at: RequestTimestamp
    follow_up_at: RequestTimestamp
