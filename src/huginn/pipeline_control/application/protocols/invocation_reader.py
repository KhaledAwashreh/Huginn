from typing import Protocol
from uuid import UUID

from huginn.pipeline_control.application.read_models.event_entry import EventEntry
from huginn.pipeline_control.application.read_models.invocation_detail import (
    InvocationDetail,
)
from huginn.pipeline_control.application.read_models.invocation_summary import (
    InvocationSummary,
)


class InvocationReader(Protocol):
    def get(self, invocation_id: UUID) -> InvocationDetail | None: ...

    def list(
        self, limit: int, offset: int, state: str | None
    ) -> tuple[InvocationSummary, ...]: ...

    def events(
        self, invocation_id: UUID, after: int, limit: int
    ) -> tuple[EventEntry, ...]: ...
