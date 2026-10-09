from typing import Protocol

from huginn.pipeline_control.domain.value_objects.pipeline_event import PipelineEvent


class InvocationEventRepository(Protocol):
    def append(self, event: PipelineEvent, transition_key: str) -> None: ...
