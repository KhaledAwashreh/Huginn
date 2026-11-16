"""Canonical current Prospect fields embedded in other read responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class ProspectSummaryResponse(ResponseModel):
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
