from typing import Literal

from pydantic import Field

from huginn.management.presentation.api.requests.common import RequestModel


class ListUserResultsQuery(RequestModel):
    limit: int = Field(default=20, strict=False, ge=1, le=100)
    offset: int = Field(default=0, strict=False, ge=0, le=9_223_372_036_854_775_807)
    state: (
        Literal[
            "pending",
            "running",
            "succeeded",
            "disabled_user",
            "user_not_found",
            "failed",
            "commit_outcome_unknown",
            "not_executed",
        ]
        | None
    ) = None
