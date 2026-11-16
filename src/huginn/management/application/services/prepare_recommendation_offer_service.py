"""Prepare a shared Business/Company claim for one explicitly selected offer."""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.application.protocols.recommendation_generation import (
    RecommendationGenerationSource,
)
from huginn.management.application.requests.prepare_recommendation_offer_request import (
    PrepareRecommendationOfferRequest,
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
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

_SCOPE = "prepare_recommendation_offer"


class PrepareRecommendationOfferService:
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

    def execute(
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
                work.lock_business_company(business_id, existing.company_id)
                current_time = self._now()
                existing = work.offer_cycles.get_by_request_key(
                    business_id, request.request_key
                )
                if existing is None:
                    raise ConflictError("Offer request changed while being retried")
                self._assert_same_intent(existing, request, fingerprint)
                response, changed = self._response_for_existing(
                    work, existing, current_time
                )
                if changed:
                    work.commit()
                return response

            recommendation = work.recommendations.get_owned(
                business_id, request.recommendation_id
            )
            revision = work.assessment_revisions.get_owned(
                business_id, request.recommendation_id, request.assessment_revision_id
            )
            if recommendation is None or revision is None:
                raise NotFoundError("Recommendation selection not found")
            if recommendation.company_id != revision.company_id:
                raise NotFoundError("Recommendation selection not found")
            work.lock_business_company(business_id, revision.company_id)
            now = self._now()
            source = self._source(work)
            existing = work.offer_cycles.get_by_request_key(
                business_id, request.request_key
            )
            if existing is not None:
                self._assert_same_intent(existing, request, fingerprint)
                response, changed = self._response_for_existing(work, existing, now)
                if changed:
                    work.commit()
                return response

            selection = load_current_offer_selection(
                work,
                source,
                business_id,
                principal.user_id,
                request.recommendation_id,
                request.assessment_revision_id,
                now,
            )
            assert_assessed_after_last_cooldown(
                work,
                business_id,
                selection.revision.company_id,
                selection.revision.assessed_at,
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
                pending = work.offer_cycles.get_pending(
                    business_id, selection.company.company_id
                )
            self._assert_company_eligible(
                source, business_id, selection.company.company_id, now
            )
            if pending is not None:
                raise ConflictError("Another offer is already pending for this Company")

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

    def _source(self, work: ProspectingUnitOfWork) -> RecommendationGenerationSource:
        if work.connection is None:
            raise RuntimeError("Offer preparation UOW has no connection")
        return self._source_factory(work.connection)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Offer preparation clock must include a timezone")
        return now

    @staticmethod
    def _assert_same_intent(cycle, request, fingerprint) -> None:
        if (
            cycle.payload_fingerprint != fingerprint
            or cycle.recommendation_id != request.recommendation_id
            or cycle.selected_revision_id != request.assessment_revision_id
        ):
            raise ConflictError("Offer request key was reused for changed intent")

    def _response_for_existing(self, work, cycle, now):
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
    def _assert_company_eligible(source, business_id, company_id, now):
        states = source.company_states(business_id, (company_id,), now)
        if len(states) != 1:
            raise RuntimeError("Company state projection did not match its request")
        from huginn.matchmaking.domain.policies.recommendation_eligibility import (
            assess_recommendation_eligibility,
        )

        if not assess_recommendation_eligibility(states[0], now).eligible:
            raise ConflictError("Company is blocked from a new offer")


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
