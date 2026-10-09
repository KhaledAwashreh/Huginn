from pydantic import Field

from huginn.management.presentation.api.requests.common import RequestModel


class ListEventsQuery(RequestModel):
    limit: int = Field(default=50, strict=False, ge=1, le=100)
    after_sequence: int = Field(
        default=0, strict=False, ge=0, le=9_223_372_036_854_775_807
    )
