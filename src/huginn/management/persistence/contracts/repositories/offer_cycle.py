from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from huginn.management.domain.entities.offer_cycle import OfferCycle
from huginn.management.domain.value_objects.accepted_offer_cadence import (
    AcceptedOfferCadence,
)


class OfferCycleRepository(Protocol):
    def get_by_request_key(
        self, business_id: UUID, idempotency_key: str
    ) -> OfferCycle | None:
        """Lookup by Business/key alone, then compare stored intent fingerprint."""
        ...

    def get_owned(
        self, business_id: UUID, company_id: UUID, cycle_id: UUID
    ) -> OfferCycle | None: ...

    def get_by_id(self, business_id: UUID, cycle_id: UUID) -> OfferCycle | None: ...

    def get_confirmed_app_presentation(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        actor_user_id: UUID,
        claim_token: str,
    ) -> OfferCycle | None:
        """Authenticate an immutable app-confirm replay by actor and token proof."""
        ...

    def get_pending(self, business_id: UUID, company_id: UUID) -> OfferCycle | None:
        """Return any active Preparing, Sending or Unknown company claim across channels."""
        ...

    def list_expired_preparing(
        self,
        business_id: UUID,
        at: datetime,
        limit: int = 100,
        company_ids: tuple[UUID, ...] | None = None,
    ) -> tuple[OfferCycle, ...]:
        """List expired Preparing claims, optionally for selected Companies."""
        ...

    def acquire_preparing(
        self,
        cycle: OfferCycle,
        *,
        now: datetime,
        lease_expires_at: datetime,
        claim_token: str,
    ) -> OfferCycle:
        """Bind the exact owned recommendation, revision and company under the pair lock."""
        ...

    def confirm_preparing(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        claim_token: str,
        confirmed_at: datetime,
        accepted_cadence: AcceptedOfferCadence,
        actor_user_id: UUID,
    ) -> OfferCycle:
        """Confirm only an owned, still-leased Preparing claim for in-app display."""
        ...

    def mark_sending(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        claim_token: str,
        started_at: datetime,
        accepted_cadence: AcceptedOfferCadence,
    ) -> OfferCycle:
        """Final serialized authorization before transport; Sending has no lease."""
        ...

    def accepted_cadence(
        self, business_id: UUID, company_id: UUID, cycle_id: UUID
    ) -> AcceptedOfferCadence | None:
        """Read the immutable cadence from app-confirm/send-authorization history."""
        ...

    def abandon_preparing(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        claim_token: str,
        actor_user_id: UUID | None,
        reason: str,
        abandoned_at: datetime,
    ) -> OfferCycle: ...
    def release_expired_preparing(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        now: datetime,
    ) -> bool:
        """Release expired Preparing only; never affects Sending or Unknown."""
        ...

    def settle_sending(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        claim_token: str,
        outcome: Literal["confirmed", "pre_send_failed", "unknown"],
        settled_at: datetime,
        presented_at: datetime | None = None,
    ) -> OfferCycle:
        """Use actual handoff time as presented_at; settled_at is observation time."""
        ...

    def resolve_unknown(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        actor_user_id: UUID,
        reason: str,
        outcome: Literal["confirmed", "abandoned"],
        presented_at: datetime | None,
        resolved_at: datetime,
    ) -> OfferCycle:
        """Require explicit actor/reason; if confirmed use actual handoff time."""
        ...
