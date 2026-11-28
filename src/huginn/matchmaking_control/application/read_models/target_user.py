from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TargetUser:
    id: UUID
    first_name: str
    last_name: str
    has_active_strategies: bool
