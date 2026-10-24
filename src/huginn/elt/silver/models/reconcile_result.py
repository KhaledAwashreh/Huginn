from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class ReconcileResult:
    status: Literal["created", "unchanged", "stale"]
    observation_id: UUID | None
