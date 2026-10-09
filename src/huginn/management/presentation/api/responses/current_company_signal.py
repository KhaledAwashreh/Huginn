"""Current company signal response; it carries no qualification claim."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class CurrentCompanySignalResponse(ResponseModel):
    id: UUID
    signal_type: str
    source: str
    source_url: str | None
    description: str | None
    stage: str | None
    occurred_at: datetime
    ingested_at: datetime
