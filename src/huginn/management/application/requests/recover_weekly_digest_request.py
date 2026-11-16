"""Explicit owner decision for a weekly digest with unknown SMTP outcome."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RecoverWeeklyDigestRequest:
    delivery_id: UUID
    reason: str
    outcome: Literal["sent", "failed"]
    accepted_at: datetime | None = None
