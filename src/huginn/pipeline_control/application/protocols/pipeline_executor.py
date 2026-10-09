from typing import Protocol
from uuid import UUID


class PipelineExecutor(Protocol):
    def run(self, invocation_id: UUID | None) -> int: ...
