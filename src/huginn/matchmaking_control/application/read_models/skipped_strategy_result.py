from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SkippedStrategyResult:
    strategy_id: UUID
    reason: str
