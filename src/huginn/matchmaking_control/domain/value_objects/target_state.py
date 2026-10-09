from enum import StrEnum


class TargetState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DISABLED_USER = "disabled_user"
    USER_NOT_FOUND = "user_not_found"
    FAILED = "failed"
    COMMIT_OUTCOME_UNKNOWN = "commit_outcome_unknown"
    NOT_EXECUTED = "not_executed"

    @property
    def is_settled(self) -> bool:
        return self not in (TargetState.PENDING, TargetState.RUNNING)

    @property
    def has_acknowledged_counts(self) -> bool:
        return self is TargetState.SUCCEEDED
