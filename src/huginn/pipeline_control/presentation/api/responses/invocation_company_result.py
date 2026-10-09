from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class InvocationCompanyResultResponse(ResponseModel):
    id: UUID
    name: str
    domain: str | None
    business_sector: list[str] | str | None
    country: str | None
    company_scale: str | None
    company_status: str | None
    stage_job_run_id: UUID
