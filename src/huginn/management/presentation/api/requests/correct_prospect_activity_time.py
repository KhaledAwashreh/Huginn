"""Strict HTTP intent for correct prospect activity time."""

from typing import Annotated

from pydantic import Field

from huginn.management.presentation.api.requests.common import (
    NonBlank,
    RequestModel,
    RequestTimestamp,
    RequestUUID,
)


class CorrectProspectActivityTimeRequest(RequestModel):
    expected_version: Annotated[int, Field(ge=1)]
    request_key: NonBlank
    original_activity_id: RequestUUID
    expected_correction_head_id: RequestUUID | None
    replacement_occurred_at: RequestTimestamp
