"""Prospect detail response with immutable origins and activity history."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.current_company import (
    CurrentCompanyResponse,
)
from huginn.management.presentation.api.responses.current_source_context import (
    CurrentSourceContextResponse,
)
from huginn.management.presentation.api.responses.prospecting_activity import (
    ProspectActivityResponse,
)
from huginn.management.presentation.api.responses.prospecting_origin import (
    ProspectOriginResponse,
)


class ProspectResponse(ResponseModel):
    id: UUID
    business_id: UUID
    company_id: UUID
    stage: Literal[
        "saved", "contacted", "in_conversation", "proposal_sent", "won_client", "closed"
    ]
    created_at: datetime
    updated_at: datetime
    version: int
    notes: str
    follow_up_at: datetime | None
    last_active_stage: (
        Literal["saved", "contacted", "in_conversation", "proposal_sent"] | None
    )
    company: CurrentCompanyResponse
    origins: list[ProspectOriginResponse]
    activities: list[ProspectActivityResponse] | None
    current_source_context: CurrentSourceContextResponse | None
