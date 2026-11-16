"""Clear exactly one active Business-owned pause block."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from huginn.management.application.requests.cancel_recommendation_pause_request import (
    CancelRecommendationPauseRequest,
)
from huginn.management.application.responses.cancel_recommendation_pause_response import (
    CancelRecommendationPauseResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.application.services.recommendation_suppression_projection import (
    remaining_recommendation_blockers,
)
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)
from huginn.management.domain.policies.command_retry import validate_command_retry
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

logger = logging.getLogger(__name__)
_SCOPE = "cancel_recommendation_pause"
_RESOURCE_KIND = "suppression_block"


class CancelRecommendationPauseService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, principal: Principal, request: CancelRecommendationPauseRequest
    ) -> CancelRecommendationPauseResponse:
        identity = CommandIdentity(
            request.request_key,
            fingerprint_command_payload(
                _SCOPE,
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
                uow.commands.get_by_key(business_id, identity.key), identity
            )
            if replay is not None:
                return replay
            initial = uow.suppression_blocks.get_owned(
                business_id, request.suppression_block_id
            )
            if initial is None:
                raise NotFoundError("Suppression block not found")
            self._require_pause(initial)
            uow.lock_business_company(business_id, initial.company_id)
            replay = self._replay(
                uow.commands.get_by_key(business_id, identity.key), identity
            )
            if replay is not None:
                return replay
            block = uow.suppression_blocks.get_owned(
                business_id, request.suppression_block_id
            )
            if block is None:
                raise NotFoundError("Suppression block not found")
            self._require_pause(block)
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("Pause cancellation clock must include a timezone")
            if block.version != request.expected_version or not block.is_active_at(now):
                raise ConflictError("Pause changed or is no longer active")
            cleared = uow.suppression_blocks.clear_one(
                business_id,
                block.company_id,
                block.id,
                request.expected_version,
                principal.user_id,
                now,
            )
            response = CancelRecommendationPauseResponse(
                cleared.id,
                cleared.version,
                now,
                self._remaining(uow, business_id, block.company_id, now),
            )
            uow.commands.record(
                CommandReceipt(
                    business_id,
                    _SCOPE,
                    identity,
                    _RESOURCE_KIND,
                    cleared.id,
                    cleared.version,
                    response.snapshot(),
                    now,
                )
            )
            uow.commit()
            logger.info(
                "Recommendation pause cancelled business=%s block=%s",
                business_id,
                cleared.id,
            )
            return response

    @staticmethod
    def _require_pause(block) -> None:
        if block.kind.value != "pause":
            raise ConflictError("Suppression block is not a pause")

    @staticmethod
    def _remaining(uow, business_id, company_id, at):
        return remaining_recommendation_blockers(
            uow.suppression_blocks.list_active(business_id, company_id, at),
            uow.prospects.get_by_business_company(business_id, company_id),
            uow.offer_cycles.get_pending(business_id, company_id),
            at=at,
        )

    @staticmethod
    def _replay(receipt, identity: CommandIdentity):
        if receipt is None:
            return None
        validate_command_retry(receipt, _SCOPE, identity)
        if receipt.resource_kind != _RESOURCE_KIND:
            raise ConflictError("Request key belongs to another command result")
        return CancelRecommendationPauseResponse.from_snapshot(receipt.result_snapshot)
