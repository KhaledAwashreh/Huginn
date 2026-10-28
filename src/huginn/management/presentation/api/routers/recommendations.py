"""Owned recommendation snapshots and append-only customer feedback."""

from uuid import UUID

from fastapi import APIRouter, Response

from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    CsrfProtected,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.requests.generate_recommendations import (
    GenerateRecommendationsRequest,
)
from huginn.management.presentation.api.requests.recommendation_feedback import (
    RecommendationFeedbackRequest,
)
from huginn.management.presentation.api.responses.recommendation_batch import (
    RecommendationBatchResponse,
)
from huginn.management.presentation.api.responses.recommendation_feedback import (
    RecommendationFeedbackResponse,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


def _private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


@router.post(
    "",
    status_code=201,
    response_model=RecommendationBatchResponse,
    responses=error_responses(401, 403, 404, 422),
)
def generate_recommendations(
    body: GenerateRecommendationsRequest,
    authenticated: CsrfProtected,
    response: Response,
    dependencies: Management,
):
    result = dependencies.recommendation_service.generate(
        authenticated.principal.user_id, body.strategy_id, body.limit
    )
    _private(response)
    return result


@router.get(
    "/latest",
    response_model=RecommendationBatchResponse,
    responses=error_responses(401, 404),
)
def latest_recommendations(
    strategy_id: UUID,
    authenticated: Authenticated,
    response: Response,
    dependencies: Management,
):
    result = dependencies.recommendation_service.latest(
        authenticated.principal.user_id, strategy_id
    )
    _private(response)
    return result


@router.get(
    "/{batch_id}",
    response_model=RecommendationBatchResponse,
    responses=error_responses(401, 404),
)
def get_recommendations(
    batch_id: UUID,
    authenticated: Authenticated,
    response: Response,
    dependencies: Management,
):
    result = dependencies.recommendation_service.get(
        authenticated.principal.user_id, batch_id
    )
    _private(response)
    return result


@router.get(
    "/{batch_id}/feedback",
    response_model=list[RecommendationFeedbackResponse],
    responses=error_responses(401, 404),
)
def list_recommendation_feedback(
    batch_id: UUID,
    authenticated: Authenticated,
    response: Response,
    dependencies: Management,
):
    result = dependencies.recommendation_service.feedback(
        authenticated.principal.user_id, batch_id
    )
    _private(response)
    return result


@router.post(
    "/{batch_id}/feedback",
    status_code=201,
    response_model=RecommendationFeedbackResponse,
    responses=error_responses(401, 403, 404, 422),
)
def save_recommendation_feedback(
    batch_id: UUID,
    body: RecommendationFeedbackRequest,
    authenticated: CsrfProtected,
    response: Response,
    dependencies: Management,
):
    feedback = RecommendationFeedback(
        body.usefulness,
        tuple(body.reasons),
        body.correction,
        body.next_step,
        body.outcome,
        body.notes,
    )
    result = dependencies.recommendation_service.review(
        authenticated.principal.user_id, batch_id, body.recommendation_id, feedback
    )
    _private(response)
    return result
