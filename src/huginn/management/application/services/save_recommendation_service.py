"""Atomic explicit discovery-to-pursuit save; ADR-0019 and design decision 7."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.responses.save_recommendation_response import (
    SaveRecommendationResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)
from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

logger = logging.getLogger(__name__)
_SCOPE = "save_recommendation"


class SaveRecommendationService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, principal: Principal, request: SaveRecommendationRequest
    ) -> SaveRecommendationResponse:
        identity = CommandIdentity(
            request.request_key,
            fingerprint_command_payload(
                _SCOPE,
                {
                    "recommendation_id": str(request.recommendation_id),
                    "assessment_revision_id": str(request.assessment_revision_id),
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
            recommendation, revision = self._membership(uow, business_id, request)
            uow.lock_business_company(business_id, revision.company_id)
            replay = self._replay(
                uow.commands.get_by_key(business_id, identity.key), identity
            )
            if replay is not None:
                return replay
            recommendation, revision = self._membership(uow, business_id, request)
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("Save clock must include a timezone")
            prospect = uow.prospects.get_by_business_company(
                business_id, revision.company_id
            )
            if prospect is None:
                prospect = uow.prospects.create(
                    Prospect(
                        uuid4(),
                        business_id,
                        revision.company_id,
                        ProspectStage("saved"),
                        now,
                        now,
                    )
                )
            appended = uow.origins.append_if_absent(
                ProspectOrigin(
                    uuid4(),
                    business_id,
                    revision.company_id,
                    prospect.id,
                    recommendation.id,
                    revision.id,
                    principal.user_id,
                    now,
                )
            )
            if appended.created:
                uow.activities.append_once(
                    business_id,
                    prospect.id,
                    identity,
                    ProspectActivity(
                        uuid4(),
                        business_id,
                        prospect.id,
                        principal.user_id,
                        ActivityKind("prospect_saved"),
                        now,
                        now,
                        {
                            "origin_id": str(appended.origin.id),
                            "recommendation_id": str(recommendation.id),
                            "assessment_revision_id": str(revision.id),
                        },
                    ),
                )
            if recommendation.status.value == "open":
                recommendation = uow.recommendations.resolve_owned(
                    business_id,
                    recommendation.id,
                    recommendation.version,
                    RecommendationStatus("converted"),
                    principal.user_id,
                    now,
                    None,
                )
            result = SaveRecommendationResponse(
                prospect.id,
                prospect.company_id,
                prospect.stage.value,
                prospect.version,
                appended.origin.id,
                recommendation.id,
                revision.id,
                recommendation.status.value,
            )
            uow.commands.record(
                CommandReceipt(
                    business_id,
                    _SCOPE,
                    identity,
                    "prospect",
                    prospect.id,
                    prospect.version,
                    result.snapshot(),
                    now,
                )
            )
            uow.commit()
            logger.info(
                "Recommendation save committed business=%s recommendation=%s prospect=%s origin_created=%s",
                business_id,
                recommendation.id,
                prospect.id,
                appended.created,
            )
            return result

    @staticmethod
    def _replay(
        receipt: CommandReceipt | None, identity: CommandIdentity
    ) -> SaveRecommendationResponse | None:
        if receipt is None:
            return None
        if (
            receipt.scope != _SCOPE
            or receipt.identity != identity
            or receipt.resource_kind != "prospect"
        ):
            raise ConflictError("Request key was already used for a different command")
        return SaveRecommendationResponse.from_snapshot(receipt.result_snapshot)

    @staticmethod
    def _membership(
        uow: ProspectingUnitOfWork,
        business_id: UUID,
        request: SaveRecommendationRequest,
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
        return recommendation, revision
