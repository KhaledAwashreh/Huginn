"""Strict HTTP intent for change prospect stage."""

from typing import Annotated, Literal

from pydantic import Field

from huginn.management.presentation.api.requests.common import (
    NonBlank,
    RequestModel,
    RequestTimestamp,
)


class ChangeProspectStageRequest(RequestModel):
    expected_version: Annotated[int, Field(ge=1)]
    request_key: NonBlank
    occurred_at: RequestTimestamp
    target_stage: Literal[
        "saved", "contacted", "in_conversation", "proposal_sent", "won_client"
    ]
    reason: str | None = None
