from dataclasses import dataclass


@dataclass(frozen=True)
class RunQueuedInvocationRequest:
    worker_id: str
