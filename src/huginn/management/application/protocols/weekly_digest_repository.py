from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)


class WeeklyDigestRepository(Protocol):
    def subscribe(self, user_id: UUID, now: datetime) -> None: ...
    def unsubscribe(self, user_id: UUID) -> None: ...
    def subscriptions(self, limit: int) -> tuple[DigestSubscription, ...]: ...
    def eligible(self, subscription: DigestSubscription) -> bool: ...
    def reserve(
        self, user_id: UUID, week_start: date, now: datetime, daily_limit: int
    ) -> UUID | None: ...
    def previous_companies(self, user_id: UUID) -> frozenset[UUID]: ...
    def prepare(
        self,
        delivery_id: UUID,
        batch_id: UUID,
        recipient: str,
        subject: str,
        body: str,
        company_ids: tuple[UUID, ...],
    ) -> None: ...
    def settle(self, delivery_id: UUID, state: str, now: datetime) -> None: ...
