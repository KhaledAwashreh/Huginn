from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class UserFailureReason(StrEnum):
    DATABASE_UNAVAILABLE = "database_unavailable"
    DATABASE_FAILURE = "database_failure"
    RETRIES_EXHAUSTED = "retries_exhausted"
    COMMIT_OUTCOME_UNKNOWN = "commit_outcome_unknown"


@dataclass(frozen=True)
class UserFailure:
    user_id: UUID
    reason: UserFailureReason
