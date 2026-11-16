"""Claim and confirm exact app assessments; ADR-0019, publication rules."""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from huginn.management.application.protocols.recommendation_generation import (
    RecommendationGenerationSource,
)
from huginn.management.application.read_models.recommendation_offer_selection import (
    RecommendationOfferSelection,
)
from huginn.management.application.requests.confirm_recommendation_offer_request import (
    ConfirmRecommendationOfferRequest,
)
from huginn.management.application.requests.prepare_recommendation_offer_request import (
    PrepareRecommendationOfferRequest,
)
from huginn.management.application.responses.confirmed_recommendation_offer_response import (
    ConfirmedRecommendationOfferResponse,
)
from huginn.management.application.responses.prepared_recommendation_offer_response import (
    PreparedRecommendationOfferResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.application.services.recommendation_offer_selection import (
    assert_assessed_after_last_cooldown,
    load_current_offer_selection,
)
from huginn.management.application.services.release_expired_preparing_offers import (
    release_expired_preparing_offers,
)
from huginn.management.domain.constants.prospecting import (
    PREPARING_OFFER_DEFAULT_LEASE,
)
from huginn.management.domain.entities.offer_cycle import OfferCycle
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)
from huginn.management.domain.value_objects.accepted_offer_cadence import (
    AcceptedOfferCadence,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)
from huginn.matchmaking.domain.policies.recommendation_eligibility import (
    assess_recommendation_eligibility,
)

_SCOPE = "prepare_recommendation_offer"


class RecommendationOfferService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        source_factory: Callable[[DatabaseSession], RecommendationGenerationSource],
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._source_factory = source_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    def prepare(
        self,
        principal: Principal,
        request: PrepareRecommendationOfferRequest,
    ) -> PreparedRecommendationOfferResponse:
        if not isinstance(principal, Principal):
            raise NotFoundError("Recommendation selection not found")
        with self._uow_factory() as identity_work:
            business_id = business_id_for_principal(principal, identity_work.businesses)
            recommendation = identity_work.recommendations.get_owned(
                business_id, request.recommendation_id
            )
            company_ids = () if recommendation is None else (recommendation.company_id,)
        release_expired_preparing_offers(
            self._uow_factory,
            business_id,
            clock=self._clock,
            company_ids=company_ids,
        )
        fingerprint = fingerprint_command_payload(
            _SCOPE,
            {
                "recommendation_id": str(request.recommendation_id),
                "assessment_revision_id": str(request.assessment_revision_id),
            },
        )
        with self._uow_factory() as work:
            business_id = business_id_for_principal(principal, work.businesses)
            existing = work.offer_cycles.get_by_request_key(
                business_id, request.request_key
            )
            if existing is not None:
                self._assert_same_intent(existing, request, fingerprint)
                company_id = existing.company_id
            else:
                recommendation = work.recommendations.get_owned(
                    business_id, request.recommendation_id
                )
                if recommendation is None:
                    raise NotFoundError("Recommendation selection not found")
                company_id = recommendation.company_id
            work.lock_business_company(business_id, company_id)
            now = self._now()
            existing = work.offer_cycles.get_by_request_key(
                business_id, request.request_key
            )
            if existing is not None:
                self._assert_same_intent(existing, request, fingerprint)
                response, changed = self._response_for_existing(work, existing, now)
                if changed:
                    work.commit()
                return response

            source = self._source(work)
            selection = self._selection(
                work,
                source,
                business_id,
                principal,
                request.recommendation_id,
                request.assessment_revision_id,
                now,
            )
            pending = work.offer_cycles.get_pending(
                business_id, selection.company.company_id
            )
            if (
                pending is not None
                and pending.status.value == "preparing"
                and pending.lease_expires_at <= now
            ):
                work.offer_cycles.release_expired_preparing(
                    business_id,
                    selection.company.company_id,
                    pending.id,
                    now,
                )
            self._assert_company_available(
                work, source, business_id, selection.company.company_id, now
            )

            claim_token = self._token_factory()
            if not claim_token:
                raise ValueError("Offer claim token generator returned an empty token")
            lease_expires_at = now + PREPARING_OFFER_DEFAULT_LEASE
            cycle = OfferCycle(
                uuid4(),
                business_id,
                selection.company.company_id,
                selection.recommendation.id,
                selection.revision.id,
                request.request_key,
                fingerprint,
                OfferCycleStatus("preparing"),
                now,
                now,
                claim_token,
                lease_expires_at,
            )
            acquired = work.offer_cycles.acquire_preparing(
                cycle,
                now=now,
                lease_expires_at=lease_expires_at,
                claim_token=claim_token,
            )
            work.commit()
            return _preparation_response(acquired)

    def confirm(
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
            selection = self._selection(
                work,
                source,
                business_id,
                principal,
                cycle.recommendation_id,
                cycle.selected_revision_id,
                now,
            )
            if selection.company.company_id != cycle.company_id:
                raise ConflictError("Offer Company changed")
            self._assert_company_available(
                work,
                source,
                business_id,
                cycle.company_id,
                now,
                exclude_offer_cycle_id=cycle.id,
            )
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
            raise RuntimeError("Recommendation offer UOW has no connection")
        return self._source_factory(work.connection)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Recommendation offer clock must include a timezone")
        return now

    @staticmethod
    def _assert_same_intent(
        cycle: OfferCycle, request: PrepareRecommendationOfferRequest, fingerprint: str
    ) -> None:
        if (
            cycle.payload_fingerprint != fingerprint
            or cycle.recommendation_id != request.recommendation_id
            or cycle.selected_revision_id != request.assessment_revision_id
        ):
            raise ConflictError("Offer request key was reused for changed intent")

    @staticmethod
    def _response_for_existing(
        work: ProspectingUnitOfWork, cycle: OfferCycle, now: datetime
    ) -> tuple[PreparedRecommendationOfferResponse, bool]:
        changed = False
        if (
            cycle.status.value == "preparing"
            and cycle.lease_expires_at is not None
            and cycle.lease_expires_at <= now
        ):
            changed = work.offer_cycles.release_expired_preparing(
                cycle.business_id, cycle.company_id, cycle.id, now
            )
            cycle = work.offer_cycles.get_owned(
                cycle.business_id, cycle.company_id, cycle.id
            )
            if cycle is None:
                raise ConflictError("Offer claim disappeared during expiry")
        return _preparation_response(cycle), changed

    @staticmethod
    def _selection(
        work: ProspectingUnitOfWork,
        source: RecommendationGenerationSource,
        business_id: UUID,
        principal: Principal,
        recommendation_id: UUID,
        revision_id: UUID,
        now: datetime,
    ) -> RecommendationOfferSelection:
        selection = load_current_offer_selection(
            work,
            source,
            business_id,
            principal.user_id,
            recommendation_id,
            revision_id,
            now,
        )
        assert_assessed_after_last_cooldown(
            work,
            business_id,
            selection.revision.company_id,
            selection.revision.assessed_at,
        )
        return selection

    @staticmethod
    def _assert_company_available(
        work: ProspectingUnitOfWork,
        source: RecommendationGenerationSource,
        business_id: UUID,
        company_id: UUID,
        now: datetime,
        *,
        exclude_offer_cycle_id: UUID | None = None,
    ) -> None:
        states = source.company_states(
            business_id,
            (company_id,),
            now,
            exclude_offer_cycle_id=exclude_offer_cycle_id,
        )
        if len(states) != 1:
            raise RuntimeError("Company state projection did not match its request")
        if not assess_recommendation_eligibility(states[0], now).eligible:
            raise ConflictError("Company is blocked from presentation")
        pending = work.offer_cycles.get_pending(business_id, company_id)
        if pending is not None and pending.id != exclude_offer_cycle_id:
            raise ConflictError("Another offer is pending for this Company")


def _preparation_response(cycle: OfferCycle) -> PreparedRecommendationOfferResponse:
    active_claim = cycle.status.value == "preparing"
    return PreparedRecommendationOfferResponse(
        cycle.id,
        cycle.recommendation_id,
        cycle.selected_revision_id,
        cycle.status,
        cycle.claim_token if active_claim else None,
        cycle.lease_expires_at if active_claim else None,
        cycle.presented_at,
    )


def _response(
    cycle: OfferCycle, cadence: AcceptedOfferCadence
) -> ConfirmedRecommendationOfferResponse:
    if cycle.presented_at is None:
        raise ConflictError("Confirmed offer has no presentation time")
    return ConfirmedRecommendationOfferResponse(
        cycle.id,
        cycle.recommendation_id,
        cycle.selected_revision_id,
        cycle.presented_at,
        cycle.presented_at + timedelta(days=cadence.repeat_interval_days),
    )
