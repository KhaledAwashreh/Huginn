from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.pipeline_control.presentation.api.responses.event_entry import (
    EventEntryResponse,
)


class EventPageResponse(ResponseModel):
    items: list[EventEntryResponse]
    next_after_sequence: int
    has_more: bool
