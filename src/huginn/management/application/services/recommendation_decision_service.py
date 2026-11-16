"""Business-owned recommendation decisions and suppression management."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.application.requests.cancel_recommendation_pause_request import (
    CancelRecommendationPauseRequest,
)
from huginn.management.application.requests.later_recommendation_request import (
    LaterRecommendationRequest,
)
from huginn.management.application.requests.mark_recommendation_not_relevant_request import (
    MarkRecommendationNotRelevantRequest,
)
from huginn.management.application.requests.reverse_recommendation_rejection_request import (
    ReverseRecommendationRejectionRequest,
)
from huginn.management.application.responses.cancel_recommendation_pause_response import (
    CancelRecommendationPauseResponse,
)
from huginn.management.application.responses.later_recommendation_response import (
    LaterRecommendationResponse,
)
from huginn.management.application.responses.mark_recommendation_not_relevant_response import (
    MarkRecommendationNotRelevantResponse,
)
from huginn.management.application.responses.reverse_recommendation_rejection_response import (
    ReverseRecommendationRejectionResponse,
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
from huginn.management.domain.policies.discovery_resolution import (
    decide_discovery,
    reverse_rejection,
)
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


class RecommendationDecisionService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def later(
        self, principal: Principal, request: LaterRecommendationRequest
    ) -> LaterRecommendationResponse:
        identity = CommandIdentity(
            request.request_key,
            fingerprint_command_payload(
                "later_recommendation",
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
                    "reason": request.reason,
                },
            ),
        )
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(principal, uow.businesses)
            prepared = self._prepare_selection(
                uow,
                business_id,
                request,
                identity,
                "later_recommendation",
                LaterRecommendationResponse,
                "Recommendation changed before Later was confirmed",
            )
            if isinstance(prepared, LaterRecommendationResponse):
                return prepared
            recommendation, revision = prepared
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
                    reason=request.reason,
                )
            )
            blockers = self._remaining(
                uow, business_id, revision.company_id, selected_at
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
            self._commit(
                uow,
                business_id,
                "later_recommendation",
                identity,
                block,
                response,
                selected_at,
            )
            logger.info(
                "Recommendation paused business=%s recommendation=%s block=%s replaced=%s",
                business_id,
                recommendation.id,
                block.id,
                current_pause.id if current_pause else None,
            )
            return response

    def mark_not_relevant(
        self, principal: Principal, request: MarkRecommendationNotRelevantRequest
    ) -> MarkRecommendationNotRelevantResponse:
        identity = CommandIdentity(
            request.request_key,
            fingerprint_command_payload(
                "mark_recommendation_not_relevant",
                {
                    "recommendation_id": str(request.recommendation_id),
                    "assessment_revision_id": str(request.assessment_revision_id),
                    "expected_recommendation_version": request.expected_recommendation_version,
                    "actor_user_id": str(principal.user_id),
                    "reason": request.reason,
                },
            ),
        )
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(principal, uow.businesses)
            prepared = self._prepare_selection(
                uow,
                business_id,
                request,
                identity,
                "mark_recommendation_not_relevant",
                MarkRecommendationNotRelevantResponse,
                "Recommendation changed before rejection",
            )
            if isinstance(prepared, MarkRecommendationNotRelevantResponse):
                return prepared
            recommendation, revision = prepared
            resolved_at = self._clock()
            if resolved_at.tzinfo is None or resolved_at.utcoffset() is None:
                raise ValueError("Rejection clock must include a timezone")
            if any(
                block.kind.value == "rejection"
                for block in uow.suppression_blocks.list_active(
                    business_id, revision.company_id, resolved_at
                )
            ):
                raise ConflictError("Company already has an active rejection")
            decision = decide_discovery(DiscoveryResolution("not_relevant"))
            reason = (
                "not_relevant"
                if request.reason is None
                else f"not_relevant: {request.reason}"
            )
            resolved = uow.recommendations.resolve_owned(
                business_id,
                recommendation.id,
                request.expected_recommendation_version,
                decision.status,
                principal.user_id,
                resolved_at,
                reason,
            )
            block = uow.suppression_blocks.append(
                SuppressionBlock(
                    id=uuid4(),
                    business_id=business_id,
                    company_id=revision.company_id,
                    kind=SuppressionKind("rejection"),
                    created_at=resolved_at,
                    effective_at=resolved_at,
                    created_by_user_id=principal.user_id,
                    reason=request.reason,
                )
            )
            blockers = self._remaining(
                uow, business_id, revision.company_id, resolved_at
            )
            response = MarkRecommendationNotRelevantResponse(
                resolved.id,
                resolved.version,
                resolved.status.value,
                block.id,
                resolved_at,
                request.reason,
                blockers,
            )
            self._commit(
                uow,
                business_id,
                "mark_recommendation_not_relevant",
                identity,
                block,
                response,
                resolved_at,
            )
            logger.info(
                "Recommendation rejected business=%s recommendation=%s block=%s",
                business_id,
                recommendation.id,
                block.id,
            )
            return response

    def cancel_pause(
        self, principal: Principal, request: CancelRecommendationPauseRequest
    ) -> CancelRecommendationPauseResponse:
        return self._clear_block(principal, request, "pause")

    def reverse_rejection(
        self, principal: Principal, request: ReverseRecommendationRejectionRequest
    ) -> ReverseRecommendationRejectionResponse:
        return self._clear_block(principal, request, "rejection")

    def _prepare_selection(
        self, uow, business_id, request, identity, scope, response_type, stale_message
    ):
        replay = self._replay(
            uow.commands.get_by_key(business_id, identity.key),
            identity,
            scope,
            response_type,
        )
        if replay is not None:
            return replay
        recommendation, revision = self._membership(uow, business_id, request)
        uow.lock_business_company(business_id, revision.company_id)
        replay = self._replay(
            uow.commands.get_by_key(business_id, identity.key),
            identity,
            scope,
            response_type,
        )
        if replay is not None:
            return replay
        recommendation, revision = self._membership(uow, business_id, request)
        self._require_open_version(
            recommendation, request.expected_recommendation_version, stale_message
        )
        return (recommendation, revision)

    def _clear_block(self, principal, request, kind):
        scope = (
            "cancel_recommendation_pause"
            if kind == "pause"
            else "reverse_recommendation_rejection"
        )
        response_type = (
            CancelRecommendationPauseResponse
            if kind == "pause"
            else ReverseRecommendationRejectionResponse
        )
        identity = CommandIdentity(
            request.request_key,
            fingerprint_command_payload(
                scope,
                {
                    "suppression_block_id": str(request.suppression_block_id),
                    "expected_version": request.expected_version,
                    "actor_user_id": str(principal.user_id),
                },
            ),
        )
        with self._uow_factory() as uow:
            business_id = business_id_for_principal(principal, uow.businesses)
            replay = self._replay(
                uow.commands.get_by_key(business_id, identity.key),
                identity,
                scope,
                response_type,
            )
            if replay is not None:
                return replay
            initial = self._owned_block(
                uow, business_id, request.suppression_block_id, kind
            )
            uow.lock_business_company(business_id, initial.company_id)
            replay = self._replay(
                uow.commands.get_by_key(business_id, identity.key),
                identity,
                scope,
                response_type,
            )
            if replay is not None:
                return replay
            block = self._owned_block(
                uow, business_id, request.suppression_block_id, kind
            )
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                message = (
                    "Pause cancellation clock must include a timezone"
                    if kind == "pause"
                    else "Rejection reversal clock must include a timezone"
                )
                raise ValueError(message)
            if block.version != request.expected_version or not block.is_active_at(now):
                message = (
                    "Pause changed or is no longer active"
                    if kind == "pause"
                    else "Rejection block changed or is no longer active"
                )
                raise ConflictError(message)
            if kind == "rejection":
                decision = reverse_rejection()
                if (
                    not decision.clear_rejection
                    or decision.reopen_recommendation
                    or decision.generate_recommendation
                ):
                    raise ConflictError(
                        "Rejection reversal policy attempted unrelated work"
                    )
            cleared = uow.suppression_blocks.clear_one(
                business_id,
                block.company_id,
                block.id,
                request.expected_version,
                principal.user_id,
                now,
            )
            response = response_type(
                cleared.id,
                cleared.version,
                now,
                self._remaining(uow, business_id, block.company_id, now),
            )
            self._commit(uow, business_id, scope, identity, cleared, response, now)
            logger.info(
                "Recommendation suppression cleared kind=%s business=%s block=%s",
                kind,
                business_id,
                cleared.id,
            )
            return response

    @staticmethod
    def _expected_pause(
        active_blocks: tuple[SuppressionBlock, ...], request: LaterRecommendationRequest
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
    def _membership(
        uow: ProspectingUnitOfWork,
        business_id,
        request: LaterRecommendationRequest | MarkRecommendationNotRelevantRequest,
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
            or (revision.business_id, revision.recommendation_id, revision.company_id)
            != (business_id, recommendation.id, recommendation.company_id)
        ):
            raise NotFoundError("Recommendation assessment not found")
        return (recommendation, revision)

    @staticmethod
    def _require_open_version(
        recommendation: Recommendation, expected_version: int, message: str
    ) -> None:
        if recommendation.status != RecommendationStatus("open"):
            raise ConflictError("Recommendation is already resolved")
        if recommendation.version != expected_version:
            raise ConflictError(message)

    @staticmethod
    def _owned_block(uow, business_id, block_id, kind):
        block = uow.suppression_blocks.get_owned(business_id, block_id)
        if block is None:
            raise NotFoundError("Suppression block not found")
        if block.kind.value != kind:
            raise ConflictError("Suppression block is not a " + kind)
        return block

    @staticmethod
    def _remaining(uow, business_id, company_id, at):
        return remaining_recommendation_blockers(
            uow.suppression_blocks.list_active(business_id, company_id, at),
            uow.prospects.get_by_business_company(business_id, company_id),
            uow.offer_cycles.get_pending(business_id, company_id),
            at=at,
        )

    @staticmethod
    def _replay(receipt, identity: CommandIdentity, scope: str, response_type):
        if receipt is None:
            return None
        validate_command_retry(receipt, scope, identity)
        if receipt.resource_kind != "suppression_block":
            raise ConflictError("Request key belongs to another command result")
        return response_type.from_snapshot(receipt.result_snapshot)

    @staticmethod
    def _commit(uow, business_id, scope, identity, block, response, at):
        uow.commands.record(
            CommandReceipt(
                business_id,
                scope,
                identity,
                "suppression_block",
                block.id,
                block.version,
                response.snapshot(),
                at,
            )
        )
        uow.commit()
