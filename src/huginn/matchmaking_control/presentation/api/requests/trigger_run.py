from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator

from huginn.management.presentation.api.requests.common import RequestModel, RequestUUID
from huginn.matchmaking_control.presentation.api.requests.all_eligible_target import (
    AllEligibleTargetBody,
)
from huginn.matchmaking_control.presentation.api.requests.single_user_target import (
    SingleUserTargetBody,
)


class TriggerRunBody(RequestModel):
    target: Annotated[
        SingleUserTargetBody | AllEligibleTargetBody, Field(discriminator="kind")
    ]
    request_id: RequestUUID
    cutoff: datetime = Field(strict=False)
    as_of: datetime | None = Field(default=None, strict=False)

    @field_validator("cutoff", "as_of", mode="before")
    @classmethod
    def timestamp_input(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("timestamp must be an ISO-8601 string")
        return value

    @field_validator("cutoff", "as_of")
    @classmethod
    def aware_timestamp(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamp requires timezone offset")
        return value
