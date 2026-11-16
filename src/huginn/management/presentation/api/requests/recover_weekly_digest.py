from typing import Annotated, Literal

from pydantic import Field, model_validator

from huginn.management.presentation.api.requests.common import (
    NonBlank,
    RequestModel,
    RequestTimestamp,
)


class RecoverWeeklyDigestRequest(RequestModel):
    reason: Annotated[NonBlank, Field(max_length=2000)]
    outcome: Literal["sent", "failed"]
    accepted_at: RequestTimestamp | None = None

    @model_validator(mode="after")
    def require_matching_acceptance(self):
        if (self.outcome == "sent") != (self.accepted_at is not None):
            raise ValueError("Only confirmed SMTP acceptance has an acceptance time")
        return self
