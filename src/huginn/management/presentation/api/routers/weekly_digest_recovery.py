"""Explicit attributed resolution, never an automatic resend."""

from uuid import UUID

from fastapi import APIRouter, Response

from huginn.management.application.requests.recover_weekly_digest_request import (
    RecoverWeeklyDigestRequest as RecoveryCommand,
)
from huginn.management.presentation.api.dependencies.authentication import CsrfProtected
from huginn.management.presentation.api.dependencies.prospecting import (
    private_prospecting_response,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.requests.recover_weekly_digest import (
    RecoverWeeklyDigestRequest,
)
from huginn.management.presentation.api.responses.recovered_weekly_digest import (
    RecoveredWeeklyDigestResponse,
)

router = APIRouter(prefix="/api/v1/weekly-digests", tags=["weekly-digests"])


@router.post(
    "/{delivery_id}/recovery",
    response_model=RecoveredWeeklyDigestResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def recover_weekly_digest(
    delivery_id: UUID,
    body: RecoverWeeklyDigestRequest,
    authenticated: CsrfProtected,
    response: Response,
    dependencies: Management,
):
    result = dependencies.recover_weekly_digest_service.execute(
        authenticated.principal,
        RecoveryCommand(delivery_id, body.reason, body.outcome, body.accepted_at),
    )
    private_prospecting_response(response)
    return RecoveredWeeklyDigestResponse(
        id=result.id,
        state=result.state,
        version=result.version,
        accepted_at=result.accepted_at,
        settled_at=result.settled_at,
    )
