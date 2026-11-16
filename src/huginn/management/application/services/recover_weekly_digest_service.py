"""Record an explicit owner resolution of an unknown weekly delivery."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from huginn.management.application.requests.recover_weekly_digest_request import (
    RecoverWeeklyDigestRequest,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.entities.weekly_digest_delivery import (
    WeeklyDigestDelivery,
)
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)
from huginn.management.persistence.contracts.repositories.weekly_digest_content import (
    WeeklyDigestContentRepository,
)
from huginn.management.persistence.contracts.repositories.weekly_digest_delivery import (
    WeeklyDigestDeliveryRepository,
)


class RecoverWeeklyDigestService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        delivery_repository_factory: Callable[
            [ProspectingUnitOfWork], WeeklyDigestDeliveryRepository
        ],
        content_repository_factory: Callable[
            [ProspectingUnitOfWork], WeeklyDigestContentRepository
        ],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._delivery_repository = delivery_repository_factory
        self._content_repository = content_repository_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, principal: Principal, request: RecoverWeeklyDigestRequest
    ) -> WeeklyDigestDelivery:
        if not isinstance(principal, Principal):
            raise NotFoundError("Weekly digest not found")
        now = _aware(self._clock())
        accepted_at = (
            None if request.accepted_at is None else _aware(request.accepted_at)
        )
        if type(request.reason) is not str:
            raise ValueError("Unknown delivery recovery requires reason and outcome")
        reason = request.reason.strip()
        if not reason or request.outcome not in {"sent", "failed"}:
            raise ValueError("Unknown delivery recovery requires reason and outcome")
        if (request.outcome == "sent") != (accepted_at is not None):
            raise ValueError(
                "Confirmed delivery recovery requires actual acceptance time"
            )

        with self._uow_factory() as work:
            business_id = business_id_for_principal(principal, work.businesses)
            repository = self._delivery_repository(work)
            delivery = repository.get_for_update(business_id, request.delivery_id)
            if delivery is None:
                raise NotFoundError("Weekly digest not found")
            events = repository.list_events(business_id, delivery.id)
            if delivery.state != "unknown":
                for event in events:
                    if (
                        event.event_kind == "unknown_resolved"
                        and event.actor_user_id == principal.user_id
                        and event.reason == reason
                        and event.outcome == request.outcome
                        and event.accepted_at == accepted_at
                    ):
                        return delivery
                raise ConflictError("Weekly digest is no longer awaiting recovery")
            content = self._content_repository(work).get_current(
                business_id, delivery.id
            )
            if content is None:
                raise ConflictError("Unknown digest has no frozen content")
            for company_id in sorted(
                {member.company_id for member in content.members}, key=str
            ):
                work.lock_business_company(business_id, company_id)
            for member in content.members:
                cycle = work.offer_cycles.get_owned(
                    business_id, member.company_id, member.offer_cycle_id
                )
                if cycle is None or cycle.status.value != "unknown":
                    raise ConflictError("Weekly offer cycle is not awaiting recovery")
                work.offer_cycles.resolve_unknown(
                    business_id,
                    member.company_id,
                    member.offer_cycle_id,
                    principal.user_id,
                    reason,
                    "confirmed" if request.outcome == "sent" else "abandoned",
                    accepted_at,
                    now,
                )
                if request.outcome == "sent":
                    work.recommendations.record_confirmed_presentation(
                        business_id,
                        member.company_id,
                        member.recommendation_id,
                        member.offer_cycle_id,
                        member.assessment_revision_id,
                        accepted_at,
                    )
                    cadence = work.offer_cycles.accepted_cadence(
                        business_id, member.company_id, member.offer_cycle_id
                    )
                    if cadence is None:
                        raise ConflictError("Unknown offer lost accepted cadence")
                    work.suppression_blocks.append(
                        SuppressionBlock(
                            uuid4(),
                            business_id,
                            member.company_id,
                            SuppressionKind("cooldown"),
                            now,
                            effective_at=accepted_at,
                            expires_at=accepted_at
                            + timedelta(days=cadence.repeat_interval_days),
                        )
                    )
            result = repository.resolve_unknown(
                business_id,
                delivery.id,
                delivery.version,
                principal.user_id,
                reason,
                request.outcome,
                now,
                accepted_at,
            )
            work.commit()
            return result


def _aware(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("Recovery time must include a timezone")
    return value.astimezone(UTC)
