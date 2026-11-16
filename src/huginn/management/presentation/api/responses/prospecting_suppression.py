"""Owner-visible suppression decision response."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.current_company import (
    CurrentCompanyResponse,
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


class SuppressionResponse(ResponseModel):
    company_id: UUID
    company: CurrentCompanyResponse
    active_blocks: list[SuppressionBlockResponse]
    prospect: ProspectSummaryResponse | None
    selection_state: ProspectingSelectionStateResponse
    selection_blockers: list[str]
    read_at: datetime
