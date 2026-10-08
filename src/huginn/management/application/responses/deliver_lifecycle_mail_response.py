"""Secret-free lifecycle delivery outcome."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DeliverLifecycleMailResponse:
    message_id: UUID | None
    outcome: Literal["idle", "sent", "retried", "suppressed", "failed", "lost_claim"]
