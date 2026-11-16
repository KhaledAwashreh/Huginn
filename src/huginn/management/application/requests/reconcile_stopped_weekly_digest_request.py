"""Owner attestation and exact authorization fences for a stopped sender."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ReconcileStoppedWeeklyDigestRequest:
    delivery_id: UUID
    expected_version: int
    expected_content_id: UUID
    expected_sending_started_at: datetime
    expected_offer_cycle_ids: tuple[UUID, ...]
    sender_stopped: bool
    reason: str
