from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class PersistRunResult:
    run_id: UUID
    input_count: int
    captured_count: int
    excluded_count: int
    failed_count: int
    status: Literal["complete", "partial", "failed"]
