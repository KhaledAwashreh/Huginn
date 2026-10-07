from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.domain.errors.criteria import CriteriaIssueReason


@dataclass(frozen=True)
class SkippedStrategy:
    strategy_id: UUID
    reason: CriteriaIssueReason
