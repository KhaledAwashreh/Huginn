"""Business-owned pursuit reads; queries never record presentation."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    CsrfProtected,
)
from huginn.management.presentation.api.dependencies.prospecting import (
    private_prospecting_response,
    prospecting_page,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.prospecting_mapping import (
    prospect_command_response,
    prospect_response,
)
from huginn.management.presentation.api.requests.change_prospect_stage import (
    ChangeProspectStageRequest,
)
from huginn.management.presentation.api.requests.clear_prospect_follow_up import (
    ClearProspectFollowUpRequest,
)
from huginn.management.presentation.api.requests.close_prospect import (
    CloseProspectRequest,
)
from huginn.management.presentation.api.requests.correct_prospect_activity_time import (
    CorrectProspectActivityTimeRequest,
)
from huginn.management.presentation.api.requests.record_proposal_draft import (
    RecordProposalDraftRequest,
)
from huginn.management.presentation.api.requests.reopen_prospect import (
    ReopenProspectRequest,
)
from huginn.management.presentation.api.requests.set_prospect_follow_up import (
    SetProspectFollowUpRequest,
)
from huginn.management.presentation.api.requests.update_prospect_notes import (
    UpdateProspectNotesRequest,
)
from huginn.management.presentation.api.responses.common import PageResponse
from huginn.management.presentation.api.responses.prospect_command import (
    ProspectCommandResponse,
)
from huginn.management.presentation.api.responses.prospecting_prospect import (
    ProspectResponse,
)

router = APIRouter(
    prefix="/api/v1/prospects",
    tags=["prospects"],
    dependencies=[Depends(private_prospecting_response)],
)


@router.get(
    "",
    response_model=PageResponse[ProspectResponse],
    responses=error_responses(401, 404, 422),
)
def list_prospects(
    authenticated: Authenticated,
    dependencies: Management,
    page: Annotated[ListProspectingRequest, Depends(prospecting_page)],
    stage: Literal[
        "saved", "contacted", "in_conversation", "proposal_sent", "won_client", "closed"
    ]
    | None = None,
):
    result = dependencies.prospecting_read_service.list_prospects(
        authenticated.principal,
        page,
        stage=None if stage is None else ProspectStage(stage),
    )
    return PageResponse[ProspectResponse](
        items=[prospect_response(item) for item in result.items],
        offset=result.offset,
        limit=result.limit,
        has_more=result.has_more,
    )


@router.get(
    "/{prospect_id}",
    response_model=ProspectResponse,
    responses=error_responses(401, 404, 422),
)
def get_prospect(
    prospect_id: UUID, authenticated: Authenticated, dependencies: Management
):
    return prospect_response(
        dependencies.prospecting_read_service.get_prospect(
            authenticated.principal, prospect_id
        )
    )


@router.post(
    "/{prospect_id}/stage",
    response_model=ProspectCommandResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def change_prospect_stage(
    prospect_id: UUID,
    body: ChangeProspectStageRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.prospect_service.change_stage(
        authenticated.principal,
        prospect_id=prospect_id,
        expected_version=body.expected_version,
        target_stage=ProspectStage(body.target_stage),
        occurred_at=body.occurred_at,
        request_key=body.request_key,
        reason=body.reason,
    )
    return prospect_command_response(result)


@router.post(
    "/{prospect_id}/close",
    response_model=ProspectCommandResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def close_prospect(
    prospect_id: UUID,
    body: CloseProspectRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.prospect_service.close(
        authenticated.principal,
        prospect_id=prospect_id,
        expected_version=body.expected_version,
        reason=body.reason,
        occurred_at=body.occurred_at,
        request_key=body.request_key,
    )
    return prospect_command_response(result)


@router.post(
    "/{prospect_id}/reopen",
    response_model=ProspectCommandResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def reopen_prospect(
    prospect_id: UUID,
    body: ReopenProspectRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.prospect_service.reopen(
        authenticated.principal,
        prospect_id=prospect_id,
        expected_version=body.expected_version,
        occurred_at=body.occurred_at,
        request_key=body.request_key,
    )
    return prospect_command_response(result)


@router.post(
    "/{prospect_id}/notes",
    response_model=ProspectCommandResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_prospect_notes(
    prospect_id: UUID,
    body: UpdateProspectNotesRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.prospect_service.update_notes(
        authenticated.principal,
        prospect_id=prospect_id,
        expected_version=body.expected_version,
        replacement_notes=body.replacement_notes,
        occurred_at=body.occurred_at,
        request_key=body.request_key,
    )
    return prospect_command_response(result)


@router.post(
    "/{prospect_id}/follow-up",
    response_model=ProspectCommandResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def set_prospect_follow_up(
    prospect_id: UUID,
    body: SetProspectFollowUpRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.prospect_service.set_follow_up(
        authenticated.principal,
        prospect_id=prospect_id,
        expected_version=body.expected_version,
        follow_up_at=body.follow_up_at,
        occurred_at=body.occurred_at,
        request_key=body.request_key,
    )
    return prospect_command_response(result)


@router.post(
    "/{prospect_id}/clear-follow-up",
    response_model=ProspectCommandResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def clear_prospect_follow_up(
    prospect_id: UUID,
    body: ClearProspectFollowUpRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.prospect_service.clear_follow_up(
        authenticated.principal,
        prospect_id=prospect_id,
        expected_version=body.expected_version,
        occurred_at=body.occurred_at,
        request_key=body.request_key,
    )
    return prospect_command_response(result)


@router.post(
    "/{prospect_id}/proposal-drafts",
    response_model=ProspectCommandResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_proposal_draft(
    prospect_id: UUID,
    body: RecordProposalDraftRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.prospect_service.record_proposal_draft(
        authenticated.principal,
        prospect_id=prospect_id,
        expected_version=body.expected_version,
        summary=body.summary,
        occurred_at=body.occurred_at,
        request_key=body.request_key,
    )
    return prospect_command_response(result)


@router.post(
    "/{prospect_id}/activity-time-corrections",
    response_model=ProspectCommandResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def correct_prospect_activity_time(
    prospect_id: UUID,
    body: CorrectProspectActivityTimeRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    result = dependencies.prospect_service.correct_activity_time(
        authenticated.principal,
        prospect_id=prospect_id,
        expected_version=body.expected_version,
        original_activity_id=body.original_activity_id,
        expected_correction_head_id=body.expected_correction_head_id,
        replacement_occurred_at=body.replacement_occurred_at,
        request_key=body.request_key,
    )
    return prospect_command_response(result)
