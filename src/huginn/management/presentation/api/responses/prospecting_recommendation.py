"""Recommendation-first view response with current eligibility context."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.current_company import (
    CurrentCompanyResponse,
)
from huginn.management.presentation.api.responses.prospecting_assessment_revision import (
    AssessmentRevisionResponse,
)
from huginn.management.presentation.api.responses.prospecting_prospect_summary import (
    ProspectSummaryResponse,
)
from huginn.management.presentation.api.responses.prospecting_selection_state import (
    ProspectingSelectionStateResponse,
)
from huginn.management.presentation.api.responses.prospecting_suppression_block import (
    SuppressionBlockResponse,
)


class RecommendationResponse(ResponseModel):
    id: UUID
    business_id: UUID
    company_id: UUID
    status: Literal["open", "converted", "rejected"]
    created_at: datetime
    updated_at: datetime
    current_revision_id: UUID | None
    first_presented_at: datetime | None
    resolved_at: datetime | None
    resolved_by_user_id: UUID | None
    resolution_reason: str | None
    version: int
    company: CurrentCompanyResponse
    assessment: AssessmentRevisionResponse | None
    prospect: ProspectSummaryResponse | None
    selection_state: ProspectingSelectionStateResponse
    selection_blockers: list[str]
    current_eligibility: Literal[
        "historical", "blocked", "unavailable", "not_reassessed"
    ]
    read_at: datetime
    evidence_state: Literal["current", "changed", "unavailable", "not_assessed"]
    active_blocks: list[SuppressionBlockResponse]
