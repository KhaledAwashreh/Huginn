from typing import Literal

from pydantic import Field

from huginn.management.presentation.api.requests.common import RequestModel


class ListRunsQuery(RequestModel):
    limit: int = Field(default=20, strict=False, ge=1, le=100)
    offset: int = Field(default=0, strict=False, ge=0, le=9_223_372_036_854_775_807)
    state: (
        Literal[
            "queued", "running", "succeeded", "completed_with_errors", "interrupted"
        ]
        | None
    ) = None
