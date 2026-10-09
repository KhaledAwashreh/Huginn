from dataclasses import dataclass

from huginn.pipeline_control.application.read_models.event_entry import EventEntry


@dataclass(frozen=True)
class ListEventsResponse:
    items: tuple[EventEntry, ...]
    next_after_sequence: int
    has_more: bool
