from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)


class DigestSubscriptionAccess(Protocol):
    def list_eligible(self, limit: int) -> tuple[DigestSubscription, ...]: ...

    def get_for_business(self, business_id: UUID) -> DigestSubscription | None: ...

    def get_for_authorization(self, business_id: UUID) -> DigestSubscription | None: ...

    def get_for_opt_out(self, business_id: UUID) -> DigestSubscription | None:
        """Lock the bound consent/recipient even when discovery is ineligible."""
        ...

    def subscribe(
        self, actor_user_id: UUID, business_id: UUID, now: datetime
    ) -> None: ...

    def unsubscribe(
        self, actor_user_id: UUID, business_id: UUID, now: datetime
    ) -> None: ...
