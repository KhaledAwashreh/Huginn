from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SkippedStrategyResultRow:
    strategy_id: UUID
    reason: str
