from enum import StrEnum


class RunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    INTERRUPTED = "interrupted"

    @property
    def is_active(self) -> bool:
        return self in (RunState.QUEUED, RunState.RUNNING)
