"""Record user feedback against the exact recommendation revision shown."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from huginn.management.application.requests.record_recommendation_feedback_request import (
    RecordRecommendationFeedbackRequest,
)
from huginn.management.application.responses.record_recommendation_feedback_response import (
    RecordRecommendationFeedbackResponse,
)
from huginn.management.application.services.business_resolution import (
    business_id_for_principal,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.entities.recommendation_assessment_feedback import (
    RecommendationAssessmentFeedback,
)
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
_SCOPE = "record_recommendation_feedback"
_RESOURCE_KIND = "recommendation_assessment_feedback"


class RecordRecommendationFeedbackService:
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
        request: RecordRecommendationFeedbackRequest,
    ) -> RecordRecommendationFeedbackResponse:
        identity = CommandIdentity(
            request.request_key,
            fingerprint_command_payload(
                _SCOPE,
                {
                    "recommendation_id": str(request.recommendation_id),
                    "assessment_revision_id": str(request.assessment_revision_id),
                    "actor_user_id": str(principal.user_id),
                    "feedback": _feedback_payload(request),
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
            recorded_at = self._clock()
            if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
                raise ValueError("Feedback clock must include a timezone")
            entry = RecommendationAssessmentFeedback(
                uuid4(),
                business_id,
                recommendation.id,
                revision.id,
                principal.user_id,
                recorded_at,
                request.feedback,
            )
            saved = uow.recommendation_feedback.append(entry)
            response = RecordRecommendationFeedbackResponse(saved)
            uow.commands.record(
                CommandReceipt(
                    business_id,
                    _SCOPE,
                    identity,
                    _RESOURCE_KIND,
                    saved.id,
                    1,
                    response.snapshot(),
                    recorded_at,
                )
            )
            uow.commit()
            logger.info(
                "Recommendation feedback recorded business=%s recommendation=%s revision=%s",
                business_id,
                recommendation.id,
                revision.id,
            )
            return response

    @staticmethod
    def _replay(
        receipt: CommandReceipt | None,
        identity: CommandIdentity,
    ) -> RecordRecommendationFeedbackResponse | None:
        if receipt is None:
            return None
        validate_command_retry(receipt, _SCOPE, identity)
        if receipt.resource_kind != _RESOURCE_KIND:
            raise ConflictError("Request key was already used for a different command")
        return RecordRecommendationFeedbackResponse.from_snapshot(
            receipt.result_snapshot
        )

    @staticmethod
    def _membership(
        uow: ProspectingUnitOfWork,
        business_id: UUID,
        request: RecordRecommendationFeedbackRequest,
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


def _feedback_payload(
    request: RecordRecommendationFeedbackRequest,
) -> dict[str, object]:
    feedback = request.feedback
    return {
        "usefulness": feedback.usefulness,
        "reasons": list(feedback.reasons),
        "correction": feedback.correction,
        "next_step": feedback.next_step,
        "outcome": feedback.outcome,
        "notes": feedback.notes,
    }
