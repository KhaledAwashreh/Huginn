"""Confirm an in-app offer only after its exact claimed revision is visible."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from huginn.management.application.protocols.recommendation_generation import (
    RecommendationGenerationSource,
)
from huginn.management.application.requests.confirm_recommendation_offer_request import (
    ConfirmRecommendationOfferRequest,
)
from huginn.management.application.responses.confirmed_recommendation_offer_response import (
    ConfirmedRecommendationOfferResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.application.services.recommendation_offer_selection import (
    assert_assessed_after_last_cooldown,
    load_current_offer_selection,
)
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.accepted_offer_cadence import (
    AcceptedOfferCadence,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)
from huginn.matchmaking.domain.policies.recommendation_eligibility import (
    assess_recommendation_eligibility,
)


class ConfirmRecommendationOfferService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        source_factory: Callable[[DatabaseSession], RecommendationGenerationSource],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._source_factory = source_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        principal: Principal,
        request: ConfirmRecommendationOfferRequest,
    ) -> ConfirmedRecommendationOfferResponse:
        if not isinstance(principal, Principal):
            raise NotFoundError("Offer cycle not found")
        with self._uow_factory() as work:
            business_id = business_id_for_principal(principal, work.businesses)
            cycle = work.offer_cycles.get_by_id(business_id, request.offer_cycle_id)
            if cycle is None:
                raise NotFoundError("Offer cycle not found")
            work.lock_business_company(business_id, cycle.company_id)
            cycle = work.offer_cycles.get_owned(
                business_id, cycle.company_id, request.offer_cycle_id
            )
            if cycle is None:
                raise NotFoundError("Offer cycle not found")

            replay = work.offer_cycles.get_confirmed_app_presentation(
                business_id,
                cycle.company_id,
                cycle.id,
                principal.user_id,
                request.claim_token,
            )
            if replay is not None:
                cadence = work.offer_cycles.accepted_cadence(
                    business_id, replay.company_id, replay.id
                )
                if cadence is None or replay.presented_at is None:
                    raise ConflictError("Confirmed offer audit is incomplete")
                return _response(replay, cadence)

            now = self._now()
            if (
                cycle.status.value != "preparing"
                or cycle.claim_token != request.claim_token
                or cycle.lease_expires_at is None
                or cycle.lease_expires_at <= now
            ):
                raise ConflictError("Offer claim expired or changed")
            source = self._source(work)
            selection = load_current_offer_selection(
                work,
                source,
                business_id,
                principal.user_id,
                cycle.recommendation_id,
                cycle.selected_revision_id,
                now,
            )
            if selection.company.company_id != cycle.company_id:
                raise ConflictError("Offer Company changed")
            assert_assessed_after_last_cooldown(
                work,
                business_id,
                cycle.company_id,
                selection.revision.assessed_at,
            )
            states = source.company_states(
                business_id,
                (cycle.company_id,),
                now,
                exclude_offer_cycle_id=cycle.id,
            )
            if (
                len(states) != 1
                or not assess_recommendation_eligibility(states[0], now).eligible
            ):
                raise ConflictError("Company is blocked from presentation")
            pending = work.offer_cycles.get_pending(business_id, cycle.company_id)
            if pending is not None and pending.id != cycle.id:
                raise ConflictError("Another offer is pending for this Company")
            preferences = work.business_recommendation_preferences.get(business_id)
            if preferences is None:
                raise NotFoundError("Business recommendation preferences not found")
            accepted = AcceptedOfferCadence(
                preferences.repeat_interval_days,
                preferences.updated_at,
                now,
            )
            confirmed = work.offer_cycles.confirm_preparing(
                business_id,
                cycle.company_id,
                cycle.id,
                request.claim_token,
                now,
                accepted,
                principal.user_id,
            )
            work.recommendations.record_confirmed_presentation(
                business_id,
                cycle.company_id,
                selection.recommendation.id,
                cycle.id,
                selection.revision.id,
                now,
            )
            cooldown_expires_at = now + timedelta(days=accepted.repeat_interval_days)
            work.suppression_blocks.append(
                SuppressionBlock(
                    uuid4(),
                    business_id,
                    cycle.company_id,
                    SuppressionKind("cooldown"),
                    now,
                    effective_at=now,
                    created_by_user_id=principal.user_id,
                    expires_at=cooldown_expires_at,
                )
            )
            work.commit()
            return _response(confirmed, accepted)

    def _source(self, work: ProspectingUnitOfWork) -> RecommendationGenerationSource:
        if work.connection is None:
            raise RuntimeError("Offer confirmation UOW has no connection")
        return self._source_factory(work.connection)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Offer confirmation clock must include a timezone")
        return now


def _response(cycle, cadence: AcceptedOfferCadence):
    if cycle.presented_at is None:
        raise ConflictError("Confirmed offer has no presentation time")
    return ConfirmedRecommendationOfferResponse(
        cycle.id,
        cycle.recommendation_id,
        cycle.selected_revision_id,
        cycle.presented_at,
        cycle.presented_at + timedelta(days=cadence.repeat_interval_days),
    )
