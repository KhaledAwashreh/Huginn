"""Atomically replace the expected active pause on an open recommendation."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.application.requests.later_recommendation_request import (
    LaterRecommendationRequest,
)
from huginn.management.application.responses.later_recommendation_response import (
    LaterRecommendationResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.application.services.recommendation_suppression_projection import (
    remaining_recommendation_blockers,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)
from huginn.management.domain.policies.command_retry import validate_command_retry
from huginn.management.domain.policies.discovery_resolution import decide_discovery
from huginn.management.domain.policies.later_pause import capture_later_pause
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.discovery_resolution import (
    DiscoveryResolution,
)
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

logger = logging.getLogger(__name__)
_SCOPE = "later_recommendation"
_RESOURCE_KIND = "suppression_block"


class LaterRecommendationService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, principal: Principal, request: LaterRecommendationRequest
    ) -> LaterRecommendationResponse:
        identity = CommandIdentity(
            request.request_key,
            fingerprint_command_payload(
                _SCOPE,
                {
                    "recommendation_id": str(request.recommendation_id),
                    "assessment_revision_id": str(request.assessment_revision_id),
                    "expected_recommendation_version": request.expected_recommendation_version,
                    "actor_user_id": str(principal.user_id),
                    "pause_choice": request.pause_choice.value,
                    "expected_repeat_interval_days": request.expected_repeat_interval_days,
                    "expected_preference_updated_at": request.expected_preference_updated_at.isoformat(),
                    "expected_pause_id": str(request.expected_pause_id)
                    if request.expected_pause_id
                    else None,
                    "expected_pause_version": request.expected_pause_version,
                },
            ),
        )
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(principal, uow.businesses)
            replay = self._replay(
                uow.commands.get_by_key(business_id, identity.key), identity
            )
            if replay is not None:
                return replay
            recommendation, revision = self._membership(uow, business_id, request)
            self._require_open_version(
                recommendation, request.expected_recommendation_version
            )
            uow.lock_business_company(business_id, revision.company_id)
            replay = self._replay(
                uow.commands.get_by_key(business_id, identity.key), identity
            )
            if replay is not None:
                return replay
            recommendation, revision = self._membership(uow, business_id, request)
            self._require_open_version(
                recommendation, request.expected_recommendation_version
            )
            selected_at = self._clock()
            if selected_at.tzinfo is None or selected_at.utcoffset() is None:
                raise ValueError("Later clock must include a timezone")
            current_pause = self._expected_pause(
                uow.suppression_blocks.list_active(
                    business_id, revision.company_id, selected_at
                ),
                request,
            )
            preferences = uow.business_recommendation_preferences.get(business_id)
            if preferences is None:
                raise NotFoundError("Business recommendation preferences not found")
            pause = capture_later_pause(
                request.pause_choice,
                repeat_interval_days=preferences.repeat_interval_days,
                preference_updated_at=preferences.updated_at,
                expected_repeat_interval_days=request.expected_repeat_interval_days,
                expected_preference_updated_at=request.expected_preference_updated_at,
                selected_at=selected_at,
            )
            decision = decide_discovery(DiscoveryResolution("later"), pause=pause)
            if not decision.add_pause or decision.status.value != "open":
                raise ConflictError("Later policy did not preserve open discovery")
            if current_pause is not None:
                uow.suppression_blocks.clear_one(
                    business_id,
                    revision.company_id,
                    current_pause.id,
                    current_pause.version,
                    principal.user_id,
                    selected_at,
                )
            block = uow.suppression_blocks.append(
                SuppressionBlock(
                    id=uuid4(),
                    business_id=business_id,
                    company_id=revision.company_id,
                    kind=SuppressionKind("pause"),
                    created_at=selected_at,
                    effective_at=selected_at,
                    created_by_user_id=principal.user_id,
                    expires_at=pause.expires_at,
                )
            )
            blockers = remaining_recommendation_blockers(
                uow.suppression_blocks.list_active(
                    business_id, revision.company_id, selected_at
                ),
                uow.prospects.get_by_business_company(business_id, revision.company_id),
                uow.offer_cycles.get_pending(business_id, revision.company_id),
                at=selected_at,
            )
            response = LaterRecommendationResponse(
                recommendation.id,
                recommendation.version,
                block.id,
                current_pause.id if current_pause else None,
                pause.choice.value,
                pause.repeat_interval_days,
                pause.preference_updated_at,
                pause.selected_at,
                pause.expires_at,
                blockers,
            )
            uow.commands.record(
                CommandReceipt(
                    business_id,
                    _SCOPE,
                    identity,
                    _RESOURCE_KIND,
                    block.id,
                    block.version,
                    response.snapshot(),
                    selected_at,
                )
            )
            uow.commit()
            logger.info(
                "Recommendation paused business=%s recommendation=%s block=%s replaced=%s",
                business_id,
                recommendation.id,
                block.id,
                current_pause.id if current_pause else None,
            )
            return response

    @staticmethod
    def _expected_pause(
        active_blocks: tuple[SuppressionBlock, ...],
        request: LaterRecommendationRequest,
    ) -> SuppressionBlock | None:
        pauses = tuple(block for block in active_blocks if block.kind.value == "pause")
        if len(pauses) > 1:
            raise ConflictError("Multiple active pauses require explicit cleanup")
        if request.expected_pause_id is None:
            if pauses:
                raise ConflictError("An active pause changed; review Later duration")
            return None
        if (
            len(pauses) != 1
            or pauses[0].id != request.expected_pause_id
            or pauses[0].version != request.expected_pause_version
        ):
            raise ConflictError("Active pause changed; review Later duration")
        return pauses[0]

    @staticmethod
    def _replay(receipt, identity: CommandIdentity):
        if receipt is None:
            return None
        validate_command_retry(receipt, _SCOPE, identity)
        if receipt.resource_kind != _RESOURCE_KIND:
            raise ConflictError("Request key belongs to another command result")
        return LaterRecommendationResponse.from_snapshot(receipt.result_snapshot)

    @staticmethod
    def _membership(
        uow: ProspectingUnitOfWork,
        business_id,
        request: LaterRecommendationRequest,
    ) -> tuple[Recommendation, AssessmentRevision]:
        recommendation = uow.recommendations.get_owned(
            business_id, request.recommendation_id
        )
        revision = uow.assessment_revisions.get_owned(
            business_id, request.recommendation_id, request.assessment_revision_id
        )
        if (
            recommendation is None
            or revision is None
            or (
                revision.business_id,
                revision.recommendation_id,
                revision.company_id,
            )
            != (business_id, recommendation.id, recommendation.company_id)
        ):
            raise NotFoundError("Recommendation assessment not found")
        return recommendation, revision

    @staticmethod
    def _require_open_version(
        recommendation: Recommendation, expected_version: int
    ) -> None:
        if recommendation.status != RecommendationStatus("open"):
            raise ConflictError("Recommendation is already resolved")
        if recommendation.version != expected_version:
            raise ConflictError("Recommendation changed before Later was confirmed")
