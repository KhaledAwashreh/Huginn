"""Reconcile a stopped sender and record explicit owner delivery outcomes."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from huginn.management.application.requests.reconcile_stopped_weekly_digest_request import (
    ReconcileStoppedWeeklyDigestRequest,
)
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
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
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

    def reconcile_stopped_sender(
        self, principal: Principal, request: ReconcileStoppedWeeklyDigestRequest
    ) -> WeeklyDigestDelivery:
        if not isinstance(principal, Principal):
            raise NotFoundError("Weekly digest not found")
        now = _aware(self._clock())
        started_at = _aware(request.expected_sending_started_at)
        if (
            request.sender_stopped is not True
            or type(request.reason) is not str
            or not request.reason.strip()
            or type(request.expected_version) is not int
            or request.expected_version < 1
            or not isinstance(request.delivery_id, UUID)
            or not isinstance(request.expected_content_id, UUID)
            or not request.expected_offer_cycle_ids
            or len(request.expected_offer_cycle_ids) > 7
            or any(
                not isinstance(value, UUID)
                for value in request.expected_offer_cycle_ids
            )
            or len(set(request.expected_offer_cycle_ids))
            != len(request.expected_offer_cycle_ids)
        ):
            raise ValueError(
                "Stopped sender reconciliation requires exact fences and an owner attestation"
            )
        reason = request.reason.strip()
        payload = JsonSnapshot(
            {
                "action": "stopped_sender_reconciliation",
                "expected_version": request.expected_version,
                "expected_content_id": str(request.expected_content_id),
                "expected_sending_started_at": started_at.isoformat(),
                "expected_offer_cycle_ids": sorted(
                    str(value) for value in request.expected_offer_cycle_ids
                ),
                "sender_stopped": True,
            }
        )
        with self._uow_factory() as work:
            business_id = business_id_for_principal(principal, work.businesses)
            repository = self._delivery_repository(work)
            delivery = repository.get_for_update(business_id, request.delivery_id)
            if delivery is None:
                raise NotFoundError("Weekly digest not found")
            for event in repository.list_events(business_id, delivery.id):
                if (
                    event.event_kind == "unknown"
                    and event.actor_user_id == principal.user_id
                    and event.reason == reason
                    and event.payload == payload
                ):
                    return delivery
            if (
                delivery.state != "sending"
                or delivery.version != request.expected_version
                or delivery.current_content_id != request.expected_content_id
                or delivery.sending_started_at != started_at
            ):
                raise ConflictError(
                    "Weekly digest is not the expected Sending authorization"
                )
            content = self._content_repository(work).get_current(
                business_id, delivery.id
            )
            if (
                content is None
                or content.id != request.expected_content_id
                or {member.offer_cycle_id for member in content.members}
                != set(request.expected_offer_cycle_ids)
            ):
                raise ConflictError("Weekly digest frozen members changed")
            for company_id in sorted(
                {member.company_id for member in content.members}, key=str
            ):
                work.lock_business_company(business_id, company_id)
            cycles = []
            for member in content.members:
                cycle = work.offer_cycles.get_owned(
                    business_id, member.company_id, member.offer_cycle_id
                )
                cadence = work.offer_cycles.accepted_cadence(
                    business_id, member.company_id, member.offer_cycle_id
                )
                if (
                    cycle is None
                    or cycle.status.value != "sending"
                    or cycle.recommendation_id != member.recommendation_id
                    or cycle.selected_revision_id != member.assessment_revision_id
                    or not cycle.claim_token
                    or cadence is None
                    or cadence.accepted_at != cycle.sending_started_at
                    or cycle.sending_started_at > started_at
                ):
                    raise ConflictError(
                        "Weekly offer cycle is not the authorized frozen member"
                    )
                cycles.append((member, cycle))
            for member, cycle in cycles:
                work.offer_cycles.settle_sending(
                    business_id,
                    member.company_id,
                    member.offer_cycle_id,
                    cycle.claim_token,
                    "unknown",
                    now,
                    actor_user_id=principal.user_id,
                    reason=reason,
                )
            result = repository.reconcile_stopped_sending(
                business_id,
                delivery.id,
                request.expected_version,
                request.expected_content_id,
                started_at,
                principal.user_id,
                reason,
                now,
                payload,
            )
            work.commit()
            return result

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
