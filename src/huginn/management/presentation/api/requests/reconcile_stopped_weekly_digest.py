from typing import Annotated

from pydantic import Field, model_validator

from huginn.management.presentation.api.requests.common import (
    NonBlank,
    RequestModel,
    RequestTimestamp,
    RequestUUID,
)


class ReconcileStoppedWeeklyDigestRequest(RequestModel):
    expected_version: Annotated[int, Field(ge=1)]
    expected_content_id: RequestUUID
    expected_sending_started_at: RequestTimestamp
    expected_offer_cycle_ids: Annotated[
        list[RequestUUID], Field(min_length=1, max_length=7)
    ]
    sender_stopped: bool
    reason: Annotated[NonBlank, Field(max_length=2000)]

    @model_validator(mode="after")
    def require_stopped_sender_and_distinct_cycles(self):
        if not self.sender_stopped or len(set(self.expected_offer_cycle_ids)) != len(
            self.expected_offer_cycle_ids
        ):
            raise ValueError(
                "Require stopped sender attestation and distinct exact cycles"
            )
        return self
