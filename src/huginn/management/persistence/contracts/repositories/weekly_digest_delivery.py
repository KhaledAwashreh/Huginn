from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from huginn.management.domain.entities.weekly_digest_delivery import (
    WeeklyDigestDelivery,
)
from huginn.management.domain.entities.weekly_digest_delivery_event import (
    WeeklyDigestDeliveryEvent,
)
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot

DigestDeliveryOutcome = Literal[
    "sent",
    "unknown",
    "pre_send_failed",
    "preparation_failed",
    "empty",
    "suppressed",
]


class WeeklyDigestDeliveryRepository(Protocol):
    def reconcile_stopped_sending(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        expected_content_id: UUID,
        expected_sending_started_at: datetime,
        actor_user_id: UUID,
        reason: str,
        recorded_at: datetime,
        payload: JsonSnapshot,
    ) -> WeeklyDigestDelivery: ...

    def reserve(
        self,
        business_id: UUID,
        recipient_user_id: UUID,
        week_start: date,
        now: datetime,
        daily_limit: int,
    ) -> WeeklyDigestDelivery | None: ...

    def get_for_business(
        self, business_id: UUID, delivery_id: UUID
    ) -> WeeklyDigestDelivery | None: ...

    def get_for_update(
        self, business_id: UUID, delivery_id: UUID
    ) -> WeeklyDigestDelivery | None: ...

    def select_content(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        content_id: UUID,
        selected_at: datetime,
    ) -> WeeklyDigestDelivery: ...

    def authorize_sending(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        expected_content_id: UUID,
        now: datetime,
    ) -> WeeklyDigestDelivery: ...

    def settle(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        outcome: DigestDeliveryOutcome,
        recorded_at: datetime,
        accepted_at: datetime | None = None,
        reason: str | None = None,
    ) -> WeeklyDigestDelivery: ...

    def resolve_unknown(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        actor_user_id: UUID,
        reason: str,
        outcome: Literal["sent", "failed"],
        recorded_at: datetime,
        accepted_at: datetime | None = None,
    ) -> WeeklyDigestDelivery: ...

    def list_events(
        self, business_id: UUID, delivery_id: UUID
    ) -> tuple[WeeklyDigestDeliveryEvent, ...]: ...
