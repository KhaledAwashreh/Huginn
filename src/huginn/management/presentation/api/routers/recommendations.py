"""Owned recommendation snapshots and append-only customer feedback."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from huginn.management.application.requests.confirm_recommendation_offer_request import (
    ConfirmRecommendationOfferRequest as ConfirmOfferCommand,
)
from huginn.management.application.requests.generate_recommendations_request import (
    GenerateRecommendationsRequest as GenerateRequest,
)
from huginn.management.application.requests.later_recommendation_request import (
    LaterRecommendationRequest as LaterRecommendationCommand,
)
from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)
from huginn.management.application.requests.mark_recommendation_not_relevant_request import (
    MarkRecommendationNotRelevantRequest as MarkRecommendationNotRelevantCommand,
)
from huginn.management.application.requests.prepare_recommendation_offer_request import (
    PrepareRecommendationOfferRequest as PrepareOfferCommand,
)
from huginn.management.application.requests.record_recommendation_feedback_request import (
    RecordRecommendationFeedbackRequest as RecordFeedbackCommand,
)
from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest as SaveRequest,
)
from huginn.management.domain.value_objects.pause_choice import PauseChoice
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    CsrfProtected,
)
from huginn.management.presentation.api.dependencies.discovery_availability import (
    require_new_discovery_work,
)
from huginn.management.presentation.api.dependencies.prospecting import (
    private_prospecting_response,
    prospecting_page,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.mapping import response_from_domain
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.prospecting_mapping import (
    assessment_revision_response,
    recommendation_response,
)
from huginn.management.presentation.api.requests.confirm_recommendation_offer import (
    ConfirmRecommendationOfferRequest,
)
from huginn.management.presentation.api.requests.generate_recommendations import (
    GenerateRecommendationsRequest,
)
from huginn.management.presentation.api.requests.later_recommendation import (
    LaterRecommendationRequest,
)
from huginn.management.presentation.api.requests.mark_recommendation_not_relevant import (
    MarkRecommendationNotRelevantRequest,
)
from huginn.management.presentation.api.requests.prepare_recommendation_offer import (
    PrepareRecommendationOfferRequest,
)
from huginn.management.presentation.api.requests.record_recommendation_feedback import (
    RecordRecommendationFeedbackRequest,
)
from huginn.management.presentation.api.requests.save_recommendation import (
    SaveRecommendationRequest,
)
from huginn.management.presentation.api.responses.common import PageResponse
from huginn.management.presentation.api.responses.confirmed_recommendation_offer import (
    ConfirmedRecommendationOfferResponse,
)
from huginn.management.presentation.api.responses.generate_recommendations import (
    GenerateRecommendationsResponse,
)
from huginn.management.presentation.api.responses.generated_recommendation_reference import (
    GeneratedRecommendationReferenceResponse,
)
from huginn.management.presentation.api.responses.later_recommendation import (
    LaterRecommendationResponse,
)
from huginn.management.presentation.api.responses.mark_recommendation_not_relevant import (
    MarkRecommendationNotRelevantResponse,
)
from huginn.management.presentation.api.responses.prepared_recommendation_offer import (
    PreparedRecommendationOfferResponse,
)
from huginn.management.presentation.api.responses.prospecting_assessment_revision import (
    AssessmentRevisionResponse,
)
from huginn.management.presentation.api.responses.prospecting_recommendation import (
    RecommendationResponse,
)
from huginn.management.presentation.api.responses.record_recommendation_feedback import (
    RecordRecommendationFeedbackResponse,
)
from huginn.management.presentation.api.responses.save_recommendation import (
    SaveRecommendationResponse,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


def _private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


@router.post(
    "",
    status_code=201,
    response_model=GenerateRecommendationsResponse,
    responses=error_responses(401, 403, 404, 422, 429, 503),
)
def generate_recommendations(
    body: GenerateRecommendationsRequest,
    authenticated: CsrfProtected,
    response: Response,
    dependencies: Management,
):
    require_new_discovery_work(dependencies)
    result = dependencies.recommendation_generation_service.execute(
        authenticated.principal,
        GenerateRequest(strategy_id=body.strategy_id, limit=body.limit),
    )
    _private(response)
    return GenerateRecommendationsResponse(
        run_id=result.run_id,
        references=[
            GeneratedRecommendationReferenceResponse(
                recommendation_id=item.recommendation_id,
                revision_id=item.revision_id,
                recommendation_version=item.recommendation_version,
            )
            for item in result.references
        ],
    )


@router.get(
    "",
    response_model=PageResponse[RecommendationResponse],
    responses=error_responses(401, 404, 422),
    dependencies=[Depends(private_prospecting_response)],
)
def list_recommendations(
    authenticated: Authenticated,
    dependencies: Management,
    page: Annotated[ListProspectingRequest, Depends(prospecting_page)],
    status: Literal["open", "converted", "rejected", "dismissed", "all"] = "open",
    strategy_id: UUID | None = None,
):
    if status == "all":
        filter_status = None
    elif status == "dismissed":
        filter_status = status
    else:
        filter_status = RecommendationStatus(status)
    result = dependencies.prospecting_read_service.list_recommendations(
        authenticated.principal,
        page,
        status=filter_status,
        strategy_id=strategy_id,
    )
    return PageResponse[RecommendationResponse](
        items=[recommendation_response(item) for item in result.items],
        offset=result.offset,
        limit=result.limit,
        has_more=result.has_more,
    )


@router.get(
    "/{recommendation_id}",
    response_model=RecommendationResponse,
    responses=error_responses(401, 404, 422),
    dependencies=[Depends(private_prospecting_response)],
)
def get_recommendation(
    recommendation_id: UUID,
    authenticated: Authenticated,
    dependencies: Management,
    assessment_revision_id: UUID | None = None,
):
    return recommendation_response(
        dependencies.prospecting_read_service.get_recommendation(
            authenticated.principal,
            recommendation_id,
            assessment_revision_id=assessment_revision_id,
        )
    )


@router.get(
    "/{recommendation_id}/assessments",
    response_model=list[AssessmentRevisionResponse],
    responses=error_responses(401, 404, 422),
    dependencies=[Depends(private_prospecting_response)],
)
def list_assessments(
    recommendation_id: UUID, authenticated: Authenticated, dependencies: Management
):
    return [
        assessment_revision_response(item)
        for item in dependencies.prospecting_read_service.list_assessments(
            authenticated.principal, recommendation_id
        )
    ]


@router.post(
    "/{recommendation_id}/save",
    response_model=SaveRecommendationResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(private_prospecting_response)],
)
def save_recommendation(
    recommendation_id: UUID,
    body: SaveRecommendationRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.save_recommendation_service.execute(
        authenticated.principal,
        SaveRequest(recommendation_id, body.assessment_revision_id, body.request_key),
    )
    return response_from_domain(result, SaveRecommendationResponse)


@router.post(
    "/{recommendation_id}/not-relevant",
    response_model=MarkRecommendationNotRelevantResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(private_prospecting_response)],
)
def mark_not_relevant(
    recommendation_id: UUID,
    body: MarkRecommendationNotRelevantRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    command = MarkRecommendationNotRelevantCommand(
        recommendation_id,
        body.assessment_revision_id,
        body.expected_recommendation_version,
        body.request_key,
        body.reason,
    )
    return response_from_domain(
        dependencies.recommendation_decision_service.mark_not_relevant(
            authenticated.principal, command
        ),
        MarkRecommendationNotRelevantResponse,
    )


@router.post(
    "/{recommendation_id}/later",
    response_model=LaterRecommendationResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(private_prospecting_response)],
)
def later(
    recommendation_id: UUID,
    body: LaterRecommendationRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    command = LaterRecommendationCommand(
        recommendation_id,
        body.assessment_revision_id,
        body.expected_recommendation_version,
        PauseChoice(body.pause_choice),
        body.expected_repeat_interval_days,
        body.expected_preference_updated_at,
        body.expected_pause_id,
        body.expected_pause_version,
        body.request_key,
        body.reason,
    )
    return response_from_domain(
        dependencies.recommendation_decision_service.later(
            authenticated.principal, command
        ),
        LaterRecommendationResponse,
    )


@router.post(
    "/{recommendation_id}/feedback",
    status_code=201,
    response_model=RecordRecommendationFeedbackResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(private_prospecting_response)],
)
def record_feedback(
    recommendation_id: UUID,
    body: RecordRecommendationFeedbackRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    value = body.feedback
    feedback = RecommendationFeedback(
        value.usefulness,
        tuple(value.reasons),
        value.correction,
        value.next_step,
        value.outcome,
        value.notes,
    )
    result = dependencies.record_recommendation_feedback_service.execute(
        authenticated.principal,
        RecordFeedbackCommand(
            recommendation_id, body.assessment_revision_id, body.request_key, feedback
        ),
    )
    return response_from_domain(result.feedback, RecordRecommendationFeedbackResponse)


@router.post(
    "/{recommendation_id}/offer-preparations",
    response_model=PreparedRecommendationOfferResponse,
    responses=error_responses(401, 403, 404, 409, 422, 503),
    dependencies=[Depends(private_prospecting_response)],
)
def prepare_offer(
    recommendation_id: UUID,
    body: PrepareRecommendationOfferRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    require_new_discovery_work(dependencies)
    result = dependencies.recommendation_offer_service.prepare(
        authenticated.principal,
        PrepareOfferCommand(
            recommendation_id, body.assessment_revision_id, body.request_key
        ),
    )
    return PreparedRecommendationOfferResponse(
        offer_cycle_id=result.offer_cycle_id,
        recommendation_id=result.recommendation_id,
        assessment_revision_id=result.assessment_revision_id,
        status=result.status.value,
        claim_token=result.claim_token,
        lease_expires_at=result.lease_expires_at,
        presented_at=result.presented_at,
    )


@router.post(
    "/offer-preparations/{offer_cycle_id}/confirm",
    response_model=ConfirmedRecommendationOfferResponse,
    responses=error_responses(401, 403, 404, 409, 422, 503),
    dependencies=[Depends(private_prospecting_response)],
)
def confirm_offer(
    offer_cycle_id: UUID,
    body: ConfirmRecommendationOfferRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    require_new_discovery_work(dependencies)
    result = dependencies.recommendation_offer_service.confirm(
        authenticated.principal, ConfirmOfferCommand(offer_cycle_id, body.claim_token)
    )
    return response_from_domain(result, ConfirmedRecommendationOfferResponse)
