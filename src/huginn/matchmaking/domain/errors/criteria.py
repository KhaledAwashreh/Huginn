from dataclasses import dataclass
from enum import StrEnum


class CriteriaIssueReason(StrEnum):
    INVALID_ICP = "invalid_icp"
    INCOMPLETE_ICP = "incomplete_icp"
    UNSUPPORTED_REGION = "unsupported_region"


@dataclass(frozen=True)
class CriteriaIssue:
    reason: CriteriaIssueReason
