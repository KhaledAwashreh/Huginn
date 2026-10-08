"""Durable lifecycle delivery bookkeeping boundary."""

from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from huginn.management.application.read_models.lifecycle_mail_outbox import (
    LifecycleMailOutboxRecord,
)
from huginn.management.application.read_models.mail_delivery_claim import (
    MailDeliveryClaim,
)
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose


class LifecycleMailOutboxRepository(Protocol):
    def enqueue(self, record: LifecycleMailOutboxRecord) -> None: ...
    def last_enqueued_at(
        self, account_id: UUID, purpose: ProofPurpose
    ) -> datetime | None: ...
    def claim_due(
        self, now: datetime, *, lease_seconds: int, max_attempts: int
    ) -> MailDeliveryClaim | None: ...
    def owns_claim(self, claim: MailDeliveryClaim, now: datetime) -> bool: ...
    def settle(
        self,
        claim: MailDeliveryClaim,
        now: datetime,
        *,
        state: Literal["pending", "sent", "failed", "suppressed"],
        failure_code: str | None = None,
        next_attempt_at: datetime | None = None,
    ) -> bool: ...
