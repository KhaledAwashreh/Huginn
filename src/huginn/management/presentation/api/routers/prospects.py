"""Business-owned pursuit reads; queries never record presentation."""

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from huginn.management.application.requests.change_prospect_stage_request import (
    ChangeProspectStageRequest as ChangeProspectStageCommand,
)
from huginn.management.application.requests.clear_prospect_follow_up_request import (
    ClearProspectFollowUpRequest as ClearProspectFollowUpCommand,
)
from huginn.management.application.requests.close_prospect_request import (
    CloseProspectRequest as CloseProspectCommand,
)
from huginn.management.application.requests.correct_prospect_activity_time_request import (
    CorrectProspectActivityTimeRequest as CorrectProspectActivityTimeCommand,
)
from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)
from huginn.management.application.requests.record_proposal_draft_request import (
    RecordProposalDraftRequest as RecordProposalDraftCommand,
)
from huginn.management.application.requests.reopen_prospect_request import (
    ReopenProspectRequest as ReopenProspectCommand,
)
from huginn.management.application.requests.set_prospect_follow_up_request import (
    SetProspectFollowUpRequest as SetProspectFollowUpCommand,
)
from huginn.management.application.requests.update_prospect_notes_request import (
    UpdateProspectNotesRequest as UpdateProspectNotesCommand,
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
from huginn.management.presentation.api.prospecting_mapping import prospect_response
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
    values = body.model_dump()
    values["target_stage"] = ProspectStage(body.target_stage)
    result = dependencies.change_prospect_stage_service.execute(
        authenticated.principal,
        ChangeProspectStageCommand(prospect_id=prospect_id, **values),
    )
    return ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    )


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
    values = body.model_dump()
    result = dependencies.close_prospect_service.execute(
        authenticated.principal, CloseProspectCommand(prospect_id=prospect_id, **values)
    )
    return ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    )


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
    values = body.model_dump()
    result = dependencies.reopen_prospect_service.execute(
        authenticated.principal,
        ReopenProspectCommand(prospect_id=prospect_id, **values),
    )
    return ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    )


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
    values = body.model_dump()
    result = dependencies.update_prospect_notes_service.execute(
        authenticated.principal,
        UpdateProspectNotesCommand(prospect_id=prospect_id, **values),
    )
    return ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    )


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
    values = body.model_dump()
    result = dependencies.set_prospect_follow_up_service.execute(
        authenticated.principal,
        SetProspectFollowUpCommand(prospect_id=prospect_id, **values),
    )
    return ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    )


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
    values = body.model_dump()
    result = dependencies.clear_prospect_follow_up_service.execute(
        authenticated.principal,
        ClearProspectFollowUpCommand(prospect_id=prospect_id, **values),
    )
    return ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    )


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
    values = body.model_dump()
    result = dependencies.record_proposal_draft_service.execute(
        authenticated.principal,
        RecordProposalDraftCommand(prospect_id=prospect_id, **values),
    )
    return ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    )


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
    values = body.model_dump()
    result = dependencies.correct_prospect_activity_time_service.execute(
        authenticated.principal,
        CorrectProspectActivityTimeCommand(prospect_id=prospect_id, **values),
    )
    return ProspectCommandResponse.model_validate_json(
        json.dumps(result.snapshot().to_json_object())
    )
