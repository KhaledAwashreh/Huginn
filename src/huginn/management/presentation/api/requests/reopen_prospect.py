"""Strict HTTP intent for reopen prospect."""

from typing import Annotated

from pydantic import Field

from huginn.management.presentation.api.requests.common import (
    NonBlank,
    RequestModel,
    RequestTimestamp,
)


class ReopenProspectRequest(RequestModel):
    expected_version: Annotated[int, Field(ge=1)]
    request_key: NonBlank
    occurred_at: RequestTimestamp
