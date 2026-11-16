"""Immutable recommendation and revision attribution for a saved Prospect."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.prospecting_assessment_revision import (
    AssessmentRevisionResponse,
)


class ProspectOriginResponse(ResponseModel):
    id: UUID
    business_id: UUID
    company_id: UUID
    prospect_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    created_by_user_id: UUID
    created_at: datetime
    recommendation_status: Literal["open", "converted", "rejected"]
    recommendation_version: int
    assessment: AssessmentRevisionResponse
