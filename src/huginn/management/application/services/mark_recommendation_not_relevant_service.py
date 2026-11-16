"""Atomically resolve an open recommendation as Not relevant."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.application.requests.mark_recommendation_not_relevant_request import (
    MarkRecommendationNotRelevantRequest,
)
from huginn.management.application.responses.mark_recommendation_not_relevant_response import (
    MarkRecommendationNotRelevantResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.application.services.recommendation_suppression_projection import (
    remaining_recommendation_blockers,
)
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)
from huginn.management.domain.policies.command_retry import validate_command_retry
from huginn.management.domain.policies.discovery_resolution import decide_discovery
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
_SCOPE = "mark_recommendation_not_relevant"
_RESOURCE_KIND = "suppression_block"


class MarkRecommendationNotRelevantService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        principal: Principal,
        request: MarkRecommendationNotRelevantRequest,
    ) -> MarkRecommendationNotRelevantResponse:
        identity = CommandIdentity(
            request.request_key,
            fingerprint_command_payload(
                _SCOPE,
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
            blockers = remaining_recommendation_blockers(
                uow.suppression_blocks.list_active(
                    business_id, revision.company_id, resolved_at
                ),
                uow.prospects.get_by_business_company(business_id, revision.company_id),
                uow.offer_cycles.get_pending(business_id, revision.company_id),
                at=resolved_at,
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
            uow.commands.record(
                CommandReceipt(
                    business_id,
                    _SCOPE,
                    identity,
                    _RESOURCE_KIND,
                    block.id,
                    block.version,
                    response.snapshot(),
                    resolved_at,
                )
            )
            uow.commit()
            logger.info(
                "Recommendation rejected business=%s recommendation=%s block=%s",
                business_id,
                recommendation.id,
                block.id,
            )
            return response

    @staticmethod
    def _replay(receipt, identity: CommandIdentity):
        if receipt is None:
            return None
        validate_command_retry(receipt, _SCOPE, identity)
        if receipt.resource_kind != _RESOURCE_KIND:
            raise ConflictError("Request key belongs to another command result")
        return MarkRecommendationNotRelevantResponse.from_snapshot(
            receipt.result_snapshot
        )

    @staticmethod
    def _membership(uow, business_id, request):
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
            raise ConflictError("Recommendation changed before rejection")
